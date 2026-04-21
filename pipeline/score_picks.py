"""
score_picks.py — Scratch Research Co.

Finds articles with pending picks whose tournament has concluded,
fetches final results from ESPN, scores each pick, and updates the
MDX frontmatter in-place.

Run as Step 1 of the weekly pipeline — before fetch_data.py — so
the new article's "how did we do" section can reference scored results.

Output:
  - updates src/content/articles/**/*.mdx in-place
  - writes data/scored_picks.json (context for generate_article.py)
"""

import re
import json
import datetime
import urllib.request
import urllib.parse
import urllib.error
import unicodedata
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
ARTICLES_DIR = ROOT / "src" / "content" / "articles"

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/golf"


# ─── ESPN helpers ─────────────────────────────────────────────────────────────

def fetch_json(url: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": "ScratchResearchCo/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print(f"  [warn] HTTP {e.code} for {url}")
        return None
    except Exception as e:
        print(f"  [warn] Error fetching {url}: {e}")
        return None


def fetch_espn_results(tournament_name: str, start_date_str: str) -> list[dict]:
    """
    Fetch final leaderboard for a tournament from ESPN.
    Tries the Sunday (start + 3 days) and surrounding dates.
    Returns list of {position, name, score, rounds} or [].
    """
    try:
        start = datetime.date.fromisoformat(start_date_str)
    except ValueError:
        print(f"  [warn] Bad date: {start_date_str}")
        return []

    # Try Sunday (start+3), then Mon (start+4) in case of playoff
    candidate_dates = [start + datetime.timedelta(days=d) for d in (3, 4, 2)]

    for slug in ("pga", "european", "liv"):
        for date in candidate_dates:
            url = f"{ESPN_BASE}/{slug}/scoreboard?dates={date.strftime('%Y%m%d')}"
            data = fetch_json(url)
            if not data:
                continue

            for event in data.get("events", []):
                name = event.get("name", "")
                status = event.get("competitions", [{}])[0].get("status", {}).get("type", {}).get("name", "")

                # Fuzzy match tournament name
                if not _names_match(tournament_name, name):
                    continue

                if status not in ("STATUS_FINAL", "STATUS_COMPLETE", "Completed", "Final"):
                    print(f"  [info] {name} status={status} — not final yet")
                    return []

                print(f"  ✓ Found final results: {name} (ESPN slug={slug})")
                competitors = event.get("competitions", [{}])[0].get("competitors", [])
                leaderboard = []
                for c in competitors:
                    athlete = c.get("athlete", {})
                    pos_obj = c.get("status", {}).get("position", {})
                    pos = pos_obj.get("id", 999)
                    try:
                        pos = int(str(pos).lstrip("T"))
                    except ValueError:
                        pos = 999

                    stats = c.get("statistics", [])
                    score = next((s.get("displayValue") for s in stats if s.get("name") == "score"), "--")
                    pos_display = pos_obj.get("displayName", str(pos))

                    # Check if missed cut
                    made_cut = c.get("status", {}).get("type", {}).get("name", "") not in ("STATUS_CUT", "CUT")

                    leaderboard.append({
                        "position": pos,
                        "position_display": pos_display,
                        "name": athlete.get("displayName", ""),
                        "score": score,
                        "made_cut": made_cut,
                    })

                leaderboard.sort(key=lambda x: x["position"])
                return leaderboard

    return []


def _normalize(name: str) -> str:
    """Lowercase, strip accents, keep only letters and spaces."""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_name = nfkd.encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", "", ascii_name.lower()).strip()


def _names_match(a: str, b: str) -> bool:
    """True if two tournament names are the same event (loose match)."""
    na, nb = _normalize(a), _normalize(b)
    # Exact match
    if na == nb:
        return True
    # One contains the other (e.g. "RBC Heritage" in "RBC Heritage Presented by Boeing")
    if na in nb or nb in na:
        return True
    # Share ≥2 significant words
    words_a = {w for w in na.split() if len(w) > 3}
    words_b = {w for w in nb.split() if len(w) > 3}
    return len(words_a & words_b) >= 2


def _player_names_match(pick_name: str, espn_name: str) -> bool:
    """True if pick name and ESPN display name refer to the same player."""
    na, nb = _normalize(pick_name), _normalize(espn_name)
    if na == nb:
        return True
    # Last name match as fallback (e.g. "Morikawa" matches "Collin Morikawa")
    last_a = na.split()[-1] if na.split() else ""
    last_b = nb.split()[-1] if nb.split() else ""
    if last_a and last_b and last_a == last_b:
        first_a = na.split()[0] if len(na.split()) > 1 else ""
        first_b = nb.split()[0] if len(nb.split()) > 1 else ""
        # Allow if first names share first letter (handles nicknames)
        if first_a and first_b:
            return first_a[0] == first_b[0]
        return True
    return False


# ─── Scoring ─────────────────────────────────────────────────────────────────

def score_pick(player_name: str, leaderboard: list[dict]) -> tuple[str, str]:
    """
    Find player in leaderboard and return (result, note).
    result: 'win' | 'top5' | 'top10' | 'top20' | 'miss'
    note:   e.g. 'Won (-15)' or 'T4 (-8)' or 'T23 (+1)' or 'MC'
    """
    for entry in leaderboard:
        if _player_names_match(player_name, entry["name"]):
            pos = entry["position"]
            pos_display = entry["position_display"]
            score = entry["score"]
            made_cut = entry["made_cut"]

            if not made_cut:
                return "miss", "MC"

            if pos == 1:
                return "win", f"Won ({score})"
            elif pos <= 5:
                return "top5", f"{pos_display} ({score})"
            elif pos <= 10:
                return "top10", f"{pos_display} ({score})"
            elif pos <= 20:
                return "top20", f"{pos_display} ({score})"
            else:
                return "miss", f"{pos_display} ({score})"

    # Player not found in top results — treat as miss
    return "miss", "Not in top results"


# ─── MDX frontmatter updater ──────────────────────────────────────────────────

def parse_frontmatter_picks(content: str) -> list[dict]:
    """Extract picks list from MDX frontmatter."""
    fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        return []

    fm = fm_match.group(1)
    picks = []

    # Match each pick block: player + result + optional note
    pick_blocks = re.findall(
        r'-\s+player:\s*["\']?([^"\'\n]+)["\']?\s*\n'
        r'\s+result:\s*["\']?([^"\'\n]+)["\']?'
        r'(?:\s*\n\s+note:\s*["\']?([^"\'\n]+)["\']?)?',
        fm,
    )
    for block in pick_blocks:
        player = block[0].strip()
        result = block[1].strip()
        note = block[2].strip() if block[2] else None
        picks.append({"player": player, "result": result, "note": note})

    return picks


def update_frontmatter_picks(content: str, scored: list[dict]) -> str:
    """
    Update pick results in MDX frontmatter.
    scored: list of {player, result, note}
    """
    # Build a map of player → (result, note)
    score_map = {p["player"]: p for p in scored}

    def replace_pick(m):
        player = m.group(1).strip()
        old_result = m.group(2).strip()

        if player not in score_map or old_result != "pending":
            return m.group(0)

        new_result = score_map[player]["result"]
        note = score_map[player].get("note", "")
        indent = "    "  # 4 spaces

        replacement = f'- player: "{player}"\n{indent}result: "{new_result}"'
        if note:
            replacement += f'\n{indent}note: "{note}"'
        return replacement

    # Replace each pick block in frontmatter only
    fm_match = re.match(r"^(---\n)(.*?)(\n---)", content, re.DOTALL)
    if not fm_match:
        return content

    prefix, fm_body, suffix = fm_match.group(1), fm_match.group(2), fm_match.group(3)
    rest = content[fm_match.end():]

    updated_fm = re.sub(
        r'-\s+player:\s*["\']?([^"\'\n]+)["\']?\s*\n'
        r'\s+result:\s*["\']?([^"\'\n]+)["\']?'
        r'(?:\s*\n\s+note:\s*["\']?[^"\'\n]*["\']?)?',
        replace_pick,
        fm_body,
    )

    return prefix + updated_fm + suffix + rest


# ─── Article scanner ──────────────────────────────────────────────────────────

def find_articles_needing_scoring() -> list[dict]:
    """
    Scan all MDX files and return those with:
      - at least one pending pick
      - nextTournamentDate that is at least 3 days in the past (tournament over)
    """
    today = datetime.date.today()
    candidates = []

    for mdx_file in sorted(ARTICLES_DIR.rglob("*.mdx")):
        content = mdx_file.read_text(encoding="utf-8")
        fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if not fm_match:
            continue

        fm = fm_match.group(1)

        # Check for pending picks
        if "result: \"pending\"" not in fm and "result: 'pending'" not in fm and "result: pending" not in fm:
            continue

        # Extract nextTournamentDate
        date_match = re.search(r'nextTournamentDate:\s*["\']?(\d{4}-\d{2}-\d{2})["\']?', fm)
        if not date_match:
            continue

        try:
            tourney_start = datetime.date.fromisoformat(date_match.group(1))
        except ValueError:
            continue

        tourney_end = tourney_start + datetime.timedelta(days=3)  # Thursday + 3 = Sunday
        if today < tourney_end:
            print(f"  [skip] {mdx_file.name}: tournament ends {tourney_end}, today is {today}")
            continue

        # Extract nextTournament name
        name_match = re.search(r'nextTournament:\s*["\']?([^"\'\n]+)["\']?', fm)
        next_tournament = name_match.group(1).strip() if name_match else ""

        candidates.append({
            "file": mdx_file,
            "next_tournament": next_tournament,
            "start_date": date_match.group(1),
            "content": content,
        })
        print(f"  Found: {mdx_file.name} → picks for {next_tournament} (started {date_match.group(1)})")

    return candidates


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("\n=== Score Picks ===\n")

    articles = find_articles_needing_scoring()

    if not articles:
        print("  No articles with scoreable pending picks found.")
        # Write empty scored picks so generate_article.py doesn't break
        (DATA_DIR / "scored_picks.json").write_text(json.dumps({"scored_weeks": []}, indent=2))
        return

    all_scored_weeks = []

    for article in articles:
        mdx_file = article["file"]
        tournament = article["next_tournament"]
        start_date = article["start_date"]
        content = article["content"]

        print(f"\n  Scoring: {tournament} (started {start_date})")

        # Get ESPN leaderboard
        leaderboard = fetch_espn_results(tournament, start_date)
        if not leaderboard:
            print(f"  [warn] No final leaderboard found for {tournament} — skipping")
            continue

        print(f"  Leaderboard: {len(leaderboard)} players")
        for p in leaderboard[:5]:
            print(f"    {p['position_display']:5} {p['name']:25} {p['score']}")

        # Score each pending pick
        existing_picks = parse_frontmatter_picks(content)
        scored_picks = []
        for pick in existing_picks:
            if pick["result"] != "pending":
                scored_picks.append(pick)
                continue

            result, note = score_pick(pick["player"], leaderboard)
            scored_picks.append({"player": pick["player"], "result": result, "note": note})
            icon = {"win": "🏆", "top5": "✓", "top10": "~", "top20": "~", "miss": "✗"}.get(result, "?")
            print(f"    {icon} {pick['player']:25} → {result} ({note})")

        # Update MDX in-place
        updated_content = update_frontmatter_picks(content, scored_picks)
        if updated_content != content:
            mdx_file.write_text(updated_content, encoding="utf-8")
            print(f"  ✓ Updated {mdx_file.name}")
        else:
            print(f"  [warn] No changes written to {mdx_file.name} — check regex patterns")

        all_scored_weeks.append({
            "tournament": tournament,
            "start_date": start_date,
            "article_file": str(mdx_file.relative_to(ROOT)),
            "picks": scored_picks,
            "leaderboard_top5": leaderboard[:5],
        })

    # Write scored picks for context in generate_article.py
    output = DATA_DIR / "scored_picks.json"
    output.write_text(json.dumps({"scored_weeks": all_scored_weeks}, indent=2))
    print(f"\n✓ Scored picks written to {output}")

    # Summary
    for week in all_scored_weeks:
        wins = sum(1 for p in week["picks"] if p["result"] == "win")
        top5s = sum(1 for p in week["picks"] if p["result"] in ("win", "top5"))
        misses = sum(1 for p in week["picks"] if p["result"] == "miss")
        print(f"\n  {week['tournament']}: {wins}W / {top5s} top-5 / {misses} miss")
        for p in week["picks"]:
            print(f"    {p['player']}: {p['result']} — {p.get('note', '')}")


if __name__ == "__main__":
    main()
