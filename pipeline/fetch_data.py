"""
fetch_data.py — Scratch Research Co.

Fetches tournament data for the weekly article pipeline.
Data sources:
  - ESPN Golf API (unofficial but stable, free)
  - Cloudflare Browser Rendering for JS-heavy tour sites
  - Wikipedia for course/tournament history

Usage:
    python pipeline/fetch_data.py [--tour pga|dp|liv|all] [--date YYYY-MM-DD]

Output: writes data/tournament_data.json
"""

import os
import sys
import json
import argparse
import datetime
import re
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")
CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/golf"


# ─── HTTP helpers ────────────────────────────────────────────────────────────

def fetch_json(url: str, headers: dict = None) -> dict | list | None:
    """Simple HTTP GET returning parsed JSON."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "ScratchResearchCo/1.0 (golf-blog-automation)",
        **(headers or {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"  [warn] HTTP {e.code} fetching {url}")
        return None
    except Exception as e:
        print(f"  [warn] Error fetching {url}: {e}")
        return None


def cloudflare_crawl(url: str, render_js: bool = False) -> str | None:
    """
    Cloudflare Browser Rendering /crawl endpoint.
    Returns markdown/text of the page.
    Falls back to None if credentials not set.
    """
    if not CLOUDFLARE_API_TOKEN or not CLOUDFLARE_ACCOUNT_ID:
        print(f"  [warn] Cloudflare credentials not set, skipping: {url}")
        return None

    api_url = (
        f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}"
        f"/browser-rendering/crawl"
    )
    payload = json.dumps({
        "url": url,
        "render": render_js,
        "format": "markdown",
    }).encode()

    req = urllib.request.Request(api_url, data=payload, method="POST", headers={
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "ScratchResearchCo/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
            return data.get("result", {}).get("content") or data.get("content")
    except urllib.error.HTTPError as e:
        print(f"  [warn] Cloudflare crawl HTTP {e.code} for {url}")
        return None
    except Exception as e:
        print(f"  [warn] Cloudflare crawl error for {url}: {e}")
        return None


# ─── ESPN Golf ────────────────────────────────────────────────────────────────

def fetch_espn_tour(tour_slug: str) -> dict | None:
    """
    Fetch current/most-recent event from ESPN for a given tour.
    tour_slug: 'pga' | 'european' | 'liv'
    """
    print(f"  Fetching ESPN {tour_slug.upper()} scoreboard...")
    url = f"{ESPN_BASE}/{tour_slug}/scoreboard"
    return fetch_json(url)


def parse_espn_event(data: dict) -> dict | None:
    """Extract clean event data from ESPN scoreboard response."""
    if not data:
        return None

    events = data.get("events", [])
    if not events:
        return None

    event = events[0]
    competition = event.get("competitions", [{}])[0]

    # Venue
    venue = competition.get("venue", {})
    venue_name = venue.get("fullName", "")
    city = venue.get("address", {}).get("city", "")
    state = venue.get("address", {}).get("state", "")

    # Competitors / leaderboard
    competitors = competition.get("competitors", [])
    leaderboard = []
    for c in competitors[:20]:
        athlete = c.get("athlete", {})
        stats = c.get("statistics", [])
        score = next((s.get("displayValue") for s in stats if s.get("name") == "score"), "")
        leaderboard.append({
            "position": c.get("status", {}).get("position", {}).get("displayName", ""),
            "name": athlete.get("displayName", ""),
            "country": athlete.get("flag", {}).get("alt", ""),
            "score": score,
            "rounds": [r.get("displayValue") for r in c.get("linescores", [])],
        })

    winner = leaderboard[0] if leaderboard else {}

    return {
        "id": event.get("id"),
        "name": event.get("name", ""),
        "shortName": event.get("shortName", ""),
        "status": competition.get("status", {}).get("type", {}).get("name", ""),
        "startDate": event.get("date", ""),
        "venue": {
            "name": venue_name,
            "city": city,
            "state": state,
        },
        "leaderboard": leaderboard,
        "winner": winner,
    }


def fetch_espn_schedule(tour_slug: str) -> list[dict]:
    """Fetch upcoming schedule to find next tournament."""
    print(f"  Fetching ESPN {tour_slug.upper()} schedule...")
    today = datetime.date.today()
    year = today.year
    url = f"{ESPN_BASE}/{tour_slug}/schedule?season={year}"
    data = fetch_json(url)
    if not data:
        return []

    events = data.get("seasons", [{}])[0].get("events", []) if "seasons" in data else data.get("events", [])
    upcoming = []
    for e in events:
        try:
            event_date = datetime.date.fromisoformat(e.get("date", "")[:10])
            if event_date >= today:
                upcoming.append({
                    "name": e.get("name", ""),
                    "shortName": e.get("shortName", ""),
                    "date": e.get("date", "")[:10],
                    "venue": e.get("venue", {}).get("fullName", ""),
                    "city": e.get("venue", {}).get("address", {}).get("city", ""),
                })
        except (ValueError, AttributeError):
            continue

    return upcoming[:3]  # next 3 events


# ─── Course / History ─────────────────────────────────────────────────────────

def fetch_wikipedia_summary(search_term: str) -> str | None:
    """Fetch Wikipedia article summary for a course or tournament."""
    print(f"  Wikipedia lookup: {search_term}")
    encoded = urllib.parse.quote(search_term.replace(" ", "_"))
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
    data = fetch_json(url)
    if not data:
        return None
    return data.get("extract", "")


# ─── Main orchestrator ────────────────────────────────────────────────────────

def build_tournament_data(tours: list[str]) -> dict:
    """Collect all data for the weekly report."""
    print("\n=== Scratch Research Co. — Data Fetch ===\n")

    result = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "tours": {},
        "completed_events": [],
        "upcoming_events": [],
        "course_history": {},
    }

    tour_map = {
        "pga": ("PGA Tour", "pga"),
        "dp": ("DP World Tour", "european"),
        "liv": ("LIV Golf", "liv"),
    }

    for key in tours:
        if key not in tour_map:
            continue
        tour_name, espn_slug = tour_map[key]
        print(f"[{tour_name}]")

        raw = fetch_espn_tour(espn_slug)
        event = parse_espn_event(raw)

        if event and event.get("status") in ("STATUS_FINAL", "STATUS_COMPLETE", "Completed"):
            print(f"  ✓ Completed: {event['name']}")
            event["tour"] = tour_name
            result["completed_events"].append(event)

            # Course history
            course_name = event.get("venue", {}).get("name", "")
            if course_name and course_name not in result["course_history"]:
                wiki_text = fetch_wikipedia_summary(course_name)
                if wiki_text:
                    result["course_history"][course_name] = wiki_text

            # Tournament history
            tournament_name = event.get("name", "")
            if tournament_name:
                wiki_text = fetch_wikipedia_summary(tournament_name)
                if wiki_text:
                    result["course_history"][f"{tournament_name}_history"] = wiki_text

        elif event:
            print(f"  ~ In progress: {event['name']} ({event.get('status')})")
            event["tour"] = tour_name
            result["tours"][tour_name] = event
        else:
            print(f"  - No active event found")

        # Upcoming schedule
        upcoming = fetch_espn_schedule(espn_slug)
        result["upcoming_events"].extend(upcoming)

    # Deduplicate upcoming
    seen = set()
    deduped = []
    for e in result["upcoming_events"]:
        key_str = e.get("name", "")
        if key_str not in seen:
            seen.add(key_str)
            deduped.append(e)
    result["upcoming_events"] = deduped[:5]

    return result


def main():
    parser = argparse.ArgumentParser(description="Fetch golf tournament data")
    parser.add_argument(
        "--tours",
        default="all",
        help="Comma-separated: pga,dp,liv or 'all'",
    )
    args = parser.parse_args()

    if args.tours == "all":
        tours = ["pga", "dp", "liv"]
    else:
        tours = [t.strip() for t in args.tours.split(",")]

    data = build_tournament_data(tours)

    output_path = DATA_DIR / "tournament_data.json"
    output_path.write_text(json.dumps(data, indent=2, default=str))
    print(f"\n✓ Data written to {output_path}")

    # Summary
    print(f"\n  Completed events:  {len(data['completed_events'])}")
    for e in data["completed_events"]:
        winner = e.get("winner", {})
        print(f"    - {e['name']} ({e['tour']}) | Winner: {winner.get('name', 'TBD')} {winner.get('score', '')}")
    print(f"  Upcoming events:   {len(data['upcoming_events'])}")
    for e in data["upcoming_events"][:3]:
        print(f"    - {e['name']} ({e.get('date', '')})")


if __name__ == "__main__":
    main()
