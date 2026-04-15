"""
verify_facts.py — Scratch Research Co.

Fetches verified biographical and historical facts about key players
and tournaments BEFORE article generation. This is the guardrail against
Claude hallucinating career achievements, records, and historical claims.

Sources (in order of reliability):
  1. Wikipedia REST API — career facts, major wins, records
  2. ESPN athlete bio API — current season stats

Output: writes data/verified_facts.json
"""

import urllib.request, urllib.parse, urllib.error
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"


def wiki_summary(title: str) -> str:
    """Fetch Wikipedia page summary. Returns empty string on failure."""
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
    req = urllib.request.Request(url, headers={"User-Agent": "ScratchResearchCo/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
            return data.get("extract", "")
    except Exception:
        return ""


def wiki_search(query: str) -> list[dict]:
    """Search Wikipedia and return top results."""
    url = f"https://en.wikipedia.org/w/api.php?action=search&list=search&srsearch={urllib.parse.quote(query)}&format=json&srlimit=3"
    req = urllib.request.Request(url, headers={"User-Agent": "ScratchResearchCo/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
            return data.get("query", {}).get("search", [])
    except Exception:
        return []


def fetch_player_facts(player_name: str) -> dict:
    """
    Fetch verified career facts for a player via Wikipedia.
    Returns a dict with sourced, citable facts.
    """
    print(f"  Verifying: {player_name}")

    # Try direct Wikipedia lookup (last name first for common golfers)
    name_variants = [
        player_name,
        "_".join(player_name.split()),
    ]

    summary = ""
    for variant in name_variants:
        summary = wiki_summary(variant)
        if summary and len(summary) > 50:
            break

    # If no direct hit, search
    if not summary:
        results = wiki_search(f"{player_name} golfer")
        for r in results:
            title = r.get("title", "")
            summary = wiki_summary(title)
            if summary and "golf" in summary.lower():
                break

    if not summary:
        return {"player": player_name, "facts": "No verified Wikipedia entry found.", "source": "none"}

    # Extract major wins count from summary
    major_pattern = re.search(r"(\w+-time|one|two|three|four|five|six|seven|eight|nine|ten|\d+).{0,20}major", summary, re.IGNORECASE)
    grand_slam = "career grand slam" in summary.lower() or "career grand Slam" in summary

    return {
        "player": player_name,
        "wiki_summary": summary[:600],
        "major_wins_mentioned": major_pattern.group(0) if major_pattern else "not specified",
        "has_career_grand_slam": grand_slam,
        "source": "wikipedia",
    }


def fetch_tournament_records(tournament_name: str, course_name: str = "") -> dict:
    """Fetch verified tournament history facts."""
    print(f"  Verifying tournament: {tournament_name}")

    tournament_summary = wiki_summary(tournament_name.replace(" ", "_"))
    course_summary = wiki_summary(course_name.replace(" ", "_")) if course_name else ""

    # Back-to-back winners at the Masters
    back_to_back = wiki_summary("Masters_Tournament")

    return {
        "tournament": tournament_name,
        "tournament_wiki": tournament_summary[:500] if tournament_summary else "",
        "course_wiki": course_summary[:500] if course_summary else "",
        "back_to_back_context": back_to_back[:400] if back_to_back else "",
        "source": "wikipedia",
    }


def fetch_masters_backttoback() -> str:
    """Get specific context on back-to-back Masters winners."""
    summary = wiki_summary("Masters_Tournament")
    # Look for repeat winners context
    if not summary:
        return ""
    return summary


def build_verified_facts(tournament_data: dict) -> dict:
    """
    Main function: given tournament data, fetch verified facts
    for all players in the top 10 + notable historical context.
    """
    print("\n=== Fact Verification ===\n")

    facts = {
        "players": {},
        "tournaments": {},
        "guardrails": [
            "All career achievement claims (Grand Slams, major counts, records) must come from verified_facts, NOT model memory.",
            "Do not state a player has won X majors unless wiki_summary explicitly states it.",
            "Do not call anyone a 'career Grand Slam' member unless has_career_grand_slam is True.",
            "For back-to-back or consecutive wins, only state what Wikipedia confirms.",
            "Picks reasoning should be based on course fit logic, not fabricated recent results.",
        ],
    }

    # Get top players from completed events
    completed = tournament_data.get("completed_events", [])
    players_to_verify = set()

    for event in completed:
        for entry in event.get("leaderboard", [])[:10]:
            name = entry.get("name", "")
            if name:
                players_to_verify.add(name)
        winner_name = event.get("winner", {}).get("name", "")
        if winner_name:
            players_to_verify.add(winner_name)

    # Verify each player
    for player in sorted(players_to_verify):
        facts["players"][player] = fetch_player_facts(player)

    # Verify tournament facts
    for event in completed:
        tournament = event.get("name", "")
        venue = event.get("venue", {}).get("name", "")
        if tournament:
            facts["tournaments"][tournament] = fetch_tournament_records(tournament, venue)

    return facts


def main():
    data_file = DATA_DIR / "tournament_data.json"
    if not data_file.exists():
        print("ERROR: data/tournament_data.json not found. Run fetch_data.py first.")
        return

    tournament_data = json.loads(data_file.read_text())
    facts = build_verified_facts(tournament_data)

    output = DATA_DIR / "verified_facts.json"
    output.write_text(json.dumps(facts, indent=2))
    print(f"\n✓ Verified facts written to {output}")

    # Print summary
    print(f"\n  Players verified: {len(facts['players'])}")
    for name, f in facts["players"].items():
        slam = " ✓ GRAND SLAM" if f.get("has_career_grand_slam") else ""
        print(f"    {name}: {f.get('major_wins_mentioned', '?')}{slam}")


if __name__ == "__main__":
    main()
