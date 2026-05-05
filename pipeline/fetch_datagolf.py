"""
fetch_datagolf.py — Scratch Research Co.

Scrapes DataGolf.com via Cloudflare Browser Rendering to extract:
  - Player world rankings (DataGolf skill ratings)
  - Course fit rankings for the upcoming tournament venue
  - Course history data for the upcoming venue

Requires:
  CLOUDFLARE_API_TOKEN
  CLOUDFLARE_ACCOUNT_ID

Output: writes data/datagolf_data.json

Usage:
    python pipeline/fetch_datagolf.py --course "Harbour Town Golf Links"
"""

import os
import re
import sys
import json
import time
import argparse
import urllib.request
import urllib.error
from pathlib import Path

from courses import resolve_course, COURSE_NAME_MAP, TOURNAMENT_TO_COURSE

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")
CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")

DG_BASE = "https://datagolf.com"

# COURSE_NAME_MAP and TOURNAMENT_TO_COURSE are imported from courses.py


# ─── Cloudflare helpers ───────────────────────────────────────────────────────

def cf_content(url: str, wait_ms: int = 7000) -> str:
    """
    Fetch a fully JS-rendered page via Cloudflare Browser Rendering /content.
    Returns HTML string, or empty string on failure.
    """
    if not CLOUDFLARE_API_TOKEN or not CLOUDFLARE_ACCOUNT_ID:
        print("  [warn] Cloudflare credentials not set — skipping DataGolf scrape")
        return ""

    api = (
        f"https://api.cloudflare.com/client/v4/accounts/"
        f"{CLOUDFLARE_ACCOUNT_ID}/browser-rendering/content"
    )
    payload = json.dumps({
        "url": url,
        "gotoOptions": {"waitUntil": "load", "timeout": 45000},
        "waitForTimeout": wait_ms,
    }).encode()

    req = urllib.request.Request(api, data=payload, method="POST", headers={
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read().decode())
        result = data.get("result", "")
        return result if isinstance(result, str) else ""
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  [warn] Cloudflare {e.code} for {url}: {body[:150]}")
        # On rate limit, wait and retry once
        if e.code == 429:
            print("  [info] Rate limited — waiting 30s before retry...")
            time.sleep(30)
            try:
                with urllib.request.urlopen(req, timeout=90) as r:
                    data = json.loads(r.read().decode())
                return data.get("result", "")
            except Exception:
                return ""
        return ""
    except Exception as e:
        print(f"  [warn] Cloudflare error for {url}: {e}")
        return ""


# ─── DataGolf parsers ─────────────────────────────────────────────────────────

def _name_to_firstlast(name: str) -> str:
    """Convert 'Last, First' → 'First Last' for matching."""
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        return f"{parts[1]} {parts[0]}"
    return name


def parse_rankings(html: str) -> list[dict]:
    """
    Parse DataGolf rankings page HTML.
    Returns list of {rank, name, name_fl, tour, dg_id, ev, trend, change}.
    name = "Last, First" (DataGolf download format)
    name_fl = "First Last" (normalized for matching with course fit)
    """
    pattern = re.compile(
        r'<div class="datarow[^"]*"\s+'
        r'tour="([^"]+)"\s+'
        r'download-name="([^"]+)"\s+'
        r'name="([^"]+)"\s+'
        r'id="(\d+)"\s+'
        r'row_num="(\d+)">(.*?)(?=<div class="datarow|$)',
        re.DOTALL,
    )

    rows = []
    for m in pattern.finditer(html):
        tour, dl_name, name, dg_id, row_num, inner = m.groups()

        # Extract col values — key is first CSS class word, cleaned
        raw_vals = re.findall(r'<div class="data ([^"]+)"[^>]*value="([^"]*)"', inner)
        vals = {}
        for col_class, val in raw_vals:
            key = col_class.split()[0].replace("-col", "").replace("dgp-", "")
            if val and val not in ("--", ""):
                vals[key] = val

        try:
            ev = float(vals.get("ev", 0) or 0)
        except ValueError:
            ev = 0.0
        try:
            trend = float(vals.get("trend", 0) or 0)
        except ValueError:
            trend = 0.0
        try:
            change = int(float(vals.get("change", 0) or 0))
        except ValueError:
            change = 0

        rows.append({
            "rank": int(row_num),
            "name": dl_name,           # "Last, First"
            "name_fl": _name_to_firstlast(dl_name),  # "First Last"
            "tour": tour,
            "dg_id": dg_id,
            "ev": ev,
            "trend": trend,
            "change": change,
        })

    rows.sort(key=lambda r: r["rank"])
    return rows


def parse_course_fit(html: str) -> list[dict]:
    """
    Parse DataGolf course fit tool page HTML.
    Returns list of {rank, name, country, dg_id, adj_value} sorted by course fit rank.
    """
    pattern = re.compile(
        r'<div class="datarow"\s+'
        r'radar_name="([^"]+)"\s+'
        r'name="([^"]+)"\s+'
        r'flag="([^"]+)"\s+'
        r'id="[^"]+"\s+'
        r'dg-id="([^"]+)"\s+'
        r'row_num="(\d+)">(.*?)(?=<div class="datarow"|</div>\s*</div>\s*</div>)',
        re.DOTALL,
    )

    rows = []
    for m in pattern.finditer(html):
        radar_name, name, flag, dg_id, row_num, inner = m.groups()

        # Extract the adjustment value (course-specific performance vs. overall skill)
        vals = dict(re.findall(r'<div class="data ([^"]+)"[^>]*value="([^"]*)"', inner))
        adj_key = next((k for k in vals if "adj-col" in k), None)
        adj_val = float(vals[adj_key]) if adj_key and vals[adj_key] else 0.0

        rows.append({
            "rank": int(row_num) + 1,
            "name": name,
            "country": flag,
            "dg_id": dg_id,
            "adj_value": round(adj_val, 4),
        })

    rows.sort(key=lambda r: r["rank"])
    return rows


def resolve_course_name(course_input: str) -> str:
    """Normalize a course or tournament name to DataGolf's exact option value."""
    return resolve_course(course_input) or course_input


# ─── Main fetch ───────────────────────────────────────────────────────────────

def fetch_datagolf(course_name: str = "Harbour Town Golf Links") -> dict:
    """
    Fetch DataGolf rankings and course fit for the given venue.
    Returns a structured dict ready for the article pipeline.
    """
    course_name = resolve_course_name(course_name)
    print(f"\n=== DataGolf Scrape (course: {course_name}) ===\n")

    result = {
        "source": "datagolf.com",
        "course": course_name,
        "rankings": [],
        "course_fit": [],
        "top10_fit": [],
        "notes": [],
    }

    # 1. Global rankings
    print("  Fetching DataGolf rankings...")
    rankings_html = cf_content(f"{DG_BASE}/datagolf-rankings", wait_ms=7000)
    if rankings_html:
        result["rankings"] = parse_rankings(rankings_html)
        print(f"  ✓ Rankings: {len(result['rankings'])} players")
    else:
        print("  - Rankings: skipped (no HTML)")
        result["notes"].append("Rankings unavailable — Cloudflare credentials may be missing")

    # 2. Course fit for upcoming venue
    print(f"  Fetching course fit for {course_name}...")
    # DataGolf course fit tool defaults to Harbour Town — may need to wait longer
    # for other courses if selection requires interaction
    cf_html = cf_content(f"{DG_BASE}/course-fit-tool", wait_ms=8000)
    if cf_html:
        # Check which course is currently shown
        selected = re.search(r'<option[^>]+selected[^>]*>([^<]+)</option>', cf_html)
        shown_course = selected.group(1).strip() if selected else "unknown"
        print(f"  Course fit showing: {shown_course}")

        fit_rows = parse_course_fit(cf_html)
        result["course_fit"] = fit_rows
        result["top10_fit"] = fit_rows[:10]
        print(f"  ✓ Course fit: {len(fit_rows)} players")
        if shown_course.lower() != course_name.lower():
            result["notes"].append(
                f"Course fit page showed '{shown_course}' (not '{course_name}'). "
                "Data may be for the default course — verify manually."
            )
    else:
        print("  - Course fit: skipped (no HTML)")
        result["notes"].append("Course fit unavailable")

    # 3. Summary: find top-ranked players who also fit the course well
    if result["rankings"] and result["course_fit"]:
        # Rankings uses "Last, First" — normalize to "First Last" for matching
        rank_map = {r["name_fl"].lower(): r for r in result["rankings"]}
        fit_map = {r["name"].lower(): r for r in result["course_fit"]}

        combined = []
        for fit_row in result["course_fit"][:30]:
            name_lower = fit_row["name"].lower()
            rank_data = rank_map.get(name_lower, {})
            combined.append({
                "name": fit_row["name"],
                "country": fit_row["country"],
                "course_fit_rank": fit_row["rank"],
                "dg_world_rank": rank_data.get("rank", 999),
                "dg_skill_ev": rank_data.get("ev", 0),
                "adj_value": fit_row["adj_value"],
            })

        # Sort by a combined score: course fit rank * 0.6 + world rank * 0.4
        combined.sort(key=lambda x: x["course_fit_rank"] * 0.6 + x["dg_world_rank"] * 0.4)
        result["combined_picks_candidates"] = combined[:15]
        print(f"\n  Top picks candidates (course fit + world rank):")
        for c in combined[:10]:
            print(f"    {c['name']:25} CFit#{c['course_fit_rank']:3}  DGRank#{c['dg_world_rank']:3}  EV={c['dg_skill_ev']:.3f}")

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--course", default="", help="Upcoming venue name (auto-detected if omitted)")
    args = parser.parse_args()

    course = args.course.strip()

    # Auto-detect from tournament_data.json written by fetch_data.py
    next_tournament_name = ""
    if not course:
        tournament_file = DATA_DIR / "tournament_data.json"
        if tournament_file.exists():
            try:
                td = json.loads(tournament_file.read_text())
                next_t = td.get("next_tournament", {})
                venue = next_t.get("venue", "")
                next_tournament_name = next_t.get("name", "")
                if venue:
                    course = venue
                    print(f"  Auto-detected next venue: {course}")
                elif next_tournament_name:
                    resolved = resolve_course_name(next_tournament_name)
                    if resolved and resolved != next_tournament_name:
                        course = resolved
                        print(f"  Resolved '{next_tournament_name}' → {course}")
                    else:
                        print(f"  [warn] Could not map '{next_tournament_name}' to a course")
            except Exception:
                pass

    if not course:
        print("ERROR: No course resolved — cannot produce accurate course fit data.")
        print("  Add the upcoming tournament to TOURNAMENT_TO_COURSE in pipeline/courses.py")
        sys.exit(1)

    data = fetch_datagolf(course)

    # Fail loudly if DataGolf showed a different course than requested
    course_mismatch_notes = [n for n in data.get("notes", []) if "Course fit page showed" in n]
    if course_mismatch_notes:
        print("\nERROR: DataGolf course fit data is for the wrong course:")
        for note in course_mismatch_notes:
            print(f"  ! {note}")
        sys.exit(1)

    output = DATA_DIR / "datagolf_data.json"
    output.write_text(json.dumps(data, indent=2))
    print(f"\n✓ DataGolf data written to {output}")

    if data["notes"]:
        print("\nNotes:")
        for note in data["notes"]:
            print(f"  ! {note}")


if __name__ == "__main__":
    main()
