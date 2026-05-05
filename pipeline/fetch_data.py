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

from courses import resolve_course

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

    # Venue — ESPN often returns None or {} here, so be defensive
    venue = competition.get("venue") or {}
    venue_name = venue.get("fullName", "") if isinstance(venue, dict) else ""
    city = venue.get("address", {}).get("city", "") if isinstance(venue, dict) else ""
    state = venue.get("address", {}).get("state", "") if isinstance(venue, dict) else ""

    # Competitors / leaderboard — handle both singles (athlete) and team events (team)
    competitors = competition.get("competitors", [])
    is_team_event = competitors and "athlete" not in competitors[0] and "team" in competitors[0]
    leaderboard = []
    for c in competitors[:20]:
        stats = c.get("statistics", [])
        score = next((s.get("displayValue") for s in stats if s.get("name") == "score"), "")
        if is_team_event:
            team = c.get("team", {})
            display_name = team.get("displayName", "")
            country = ""
        else:
            athlete = c.get("athlete", {})
            display_name = athlete.get("displayName", "")
            country = athlete.get("flag", {}).get("alt", "")
        leaderboard.append({
            "position": c.get("status", {}).get("position", {}).get("displayName", ""),
            "name": display_name,
            "country": country,
            "score": score,
            "rounds": [r.get("displayValue") for r in c.get("linescores", [])],
        })

    winner = leaderboard[0] if leaderboard else {}

    tournament_name = event.get("name", "")
    resolved_course = resolve_course(tournament_name, venue_name)

    return {
        "id": event.get("id"),
        "name": tournament_name,
        "shortName": event.get("shortName", ""),
        "status": competition.get("status", {}).get("type", {}).get("name", ""),
        "startDate": event.get("date", ""),
        "format": "team" if is_team_event else "singles",
        "venue": {
            "name": resolved_course or venue_name,
            "city": city,
            "state": state,
        },
        "leaderboard": leaderboard,
        "winner": winner,
    }


def fetch_next_tournament(tour_slug: str) -> dict | None:
    """
    Find the next upcoming tournament by probing date-specific scoreboards.
    Tries Wed–Sun of next week. Returns first event found that isn't already
    complete, or None if nothing found.
    """
    today = datetime.date.today()
    # Pipeline runs Sunday night — next event typically starts Thu (+4 days)
    # Try Wed through the following Mon to be safe
    for offset in range(3, 9):
        date = today + datetime.timedelta(days=offset)
        url = f"{ESPN_BASE}/{tour_slug}/scoreboard?dates={date.strftime('%Y%m%d')}"
        data = fetch_json(url)
        if not data:
            continue
        for event in data.get("events", []):
            status = event.get("competitions", [{}])[0].get("status", {}).get("type", {}).get("name", "")
            # Skip already-completed events (the one we just covered)
            if status in ("STATUS_FINAL", "STATUS_COMPLETE", "Completed"):
                continue
            venue_obj = event.get("competitions", [{}])[0].get("venue") or {}
            venue_name = venue_obj.get("fullName", "") if isinstance(venue_obj, dict) else ""
            city = venue_obj.get("address", {}).get("city", "") if isinstance(venue_obj, dict) else ""
            event_name = event.get("name", "")
            event_date = event.get("date", "")[:10]
            if event_name:
                resolved = resolve_course(event_name, venue_name)
                return {
                    "name": event_name,
                    "shortName": event.get("shortName", ""),
                    "date": event_date,
                    "venue": resolved or venue_name,
                    "city": city,
                }
    return None


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
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "tours": {},
        "completed_events": [],
        "upcoming_events": [],
        "course_history": {},
    }

    tour_map = {
        "pga": ("PGA Tour", "pga"),
        "dp": ("DP World Tour", "eur"),
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

        # Next tournament (for DataGolf course fit lookup)
        if espn_slug == "pga" and not result.get("next_tournament"):
            next_event = fetch_next_tournament(espn_slug)
            if next_event:
                result["next_tournament"] = next_event
                result["upcoming_events"].append(next_event)
                print(f"  ✓ Next PGA event: {next_event['name']} at {next_event['venue']} ({next_event['date']})")
            else:
                print("  - Next tournament: not found via scoreboard probe")

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
