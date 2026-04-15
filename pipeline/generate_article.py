"""
generate_article.py — Scratch Research Co.

Takes tournament_data.json + picks history and generates a full article
using the Claude API with prompt caching.

Usage:
    python pipeline/generate_article.py

Requires:
    ANTHROPIC_API_KEY environment variable

Output:
    - src/content/articles/YYYY/YYYY-MM-DD-<slug>.mdx
    - picks/picks-history.json (updated)
"""

import os
import sys
import json
import re
import datetime
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "data"
ARTICLES_DIR = ROOT / "src" / "content" / "articles"
PICKS_FILE = ROOT / "picks" / "picks-history.json"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

if not ANTHROPIC_API_KEY:
    print("ERROR: ANTHROPIC_API_KEY environment variable is required")
    sys.exit(1)


# ─── Picks history ────────────────────────────────────────────────────────────

def load_picks_history() -> list[dict]:
    if PICKS_FILE.exists():
        return json.loads(PICKS_FILE.read_text())
    return []


def get_last_week_picks(history: list[dict]) -> dict | None:
    """Return the most recent pending picks entry."""
    for entry in reversed(history):
        if any(p.get("result") == "pending" for p in entry.get("picks", [])):
            return entry
    return None


def save_picks_to_history(tournament: str, date_str: str, picks: list[dict]) -> None:
    history = load_picks_history()
    history.append({
        "tournament": tournament,
        "date": date_str,
        "picks": [{"player": p, "result": "pending", "note": ""} for p in picks],
    })
    PICKS_FILE.parent.mkdir(exist_ok=True)
    PICKS_FILE.write_text(json.dumps(history, indent=2))


# ─── Claude API call ──────────────────────────────────────────────────────────

def call_claude(messages: list[dict], system: str) -> str:
    """
    Call Claude API with prompt caching on the system prompt.
    Uses urllib (no external dependencies).
    """
    import urllib.request

    model = "claude-opus-4-6"
    url = "https://api.anthropic.com/v1/messages"

    payload = {
        "model": model,
        "max_tokens": 4096,
        "system": [
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},  # prompt caching
            }
        ],
        "messages": messages,
    }

    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Content-Type": "application/json",
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "prompt-caching-2024-07-31",
    })

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())
            usage = result.get("usage", {})
            print(f"  Tokens used — input: {usage.get('input_tokens')}, "
                  f"output: {usage.get('output_tokens')}, "
                  f"cache_read: {usage.get('cache_read_input_tokens', 0)}, "
                  f"cache_write: {usage.get('cache_creation_input_tokens', 0)}")
            return result["content"][0]["text"]
    except Exception as e:
        print(f"ERROR calling Claude API: {e}")
        raise


# ─── Article generation ───────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are the writer for Scratch Research Co., a weekly golf publication.

VOICE AND TONE:
- Write like someone who genuinely loves the game and has been around it — not a broadcaster
- Observational, curious, specific. Never generic. Never corporate.
- First-person plural ("we") is fine but don't overuse it
- Dry wit is welcome. Reverence is earned, not assumed.
- Short, punchy sentences mixed with longer ones. Varied rhythm.
- No clichés. "Must-win situation", "on the precipice", "gutted out" — avoid all of it.
- Every claim should feel earned. If a stat is interesting, explain WHY it's interesting.

REFERENCE STYLE (what to sound like):
- The way someone who walked Augusta with no phone would describe it:
  "The rough is essentially non-existent — which makes sense when you see the greens up close."
- Observations, not play-by-play. Show what the numbers mean.
- History that makes the reader feel something, not just dates and names.

STRUCTURE — follow this exactly in order:
1. Intro paragraph (2-3 sentences, sets the scene, don't start with the winner's name)
2. ## The Recap — narrative of the week, key moments, what it felt like
3. ## By The Numbers — 4-6 key stats in a <div class="stat-grid"> block (see format below)
4. ## What Actually Happened — 3-5 specific moments / observations (deeper analysis)
5. ## Course & History — interesting facts about the venue and tournament history
6. ## Last Week's Picks — cross-reference previous picks if provided, otherwise skip
7. ## Looking Ahead: [Next Tournament Name] — what to watch, key storylines
8. ## Our Picks — 5 players with brief reasoning each (inside a <div class="picks-box"> block)

STAT GRID FORMAT:
<div class="stat-grid">
  <div class="stat-item"><span class="stat-number">-18</span><span class="stat-label">Winning Score</span></div>
  ... (4-6 items)
</div>

PICKS BOX FORMAT:
<div class="picks-box">
<h3>Our Picks: [Tournament]</h3>

1. **Player Name** — One sentence why. Form/course fit/stats rationale.
2. **Player Name** — ...
... (5 picks)
</div>

OUTPUT FORMAT:
Return ONLY the article body content (no frontmatter, no ```markdown fences).
Start directly with the intro paragraph.
"""


def build_user_prompt(tournament_data: dict, picks_history: list[dict]) -> str:
    """Construct the user message with all tournament context."""

    completed = tournament_data.get("completed_events", [])
    upcoming = tournament_data.get("upcoming_events", [])
    course_history = tournament_data.get("course_history", {})

    last_picks = get_last_week_picks(picks_history)

    sections = []

    # Completed events
    if completed:
        sections.append("## COMPLETED EVENTS THIS WEEK\n")
        for event in completed:
            sections.append(f"**{event.get('name')} ({event.get('tour')})**")
            venue = event.get("venue", {})
            sections.append(f"Venue: {venue.get('name')}, {venue.get('city')}, {venue.get('state')}")
            winner = event.get("winner", {})
            sections.append(f"Winner: {winner.get('name')} ({winner.get('score')})")
            sections.append("\nLeaderboard (Top 10):")
            for p in event.get("leaderboard", [])[:10]:
                sections.append(f"  {p.get('position')}. {p.get('name')} — {p.get('score')}")
            sections.append("")
    else:
        sections.append("No events completed this week yet (may still be in progress).\n")

    # Course history
    if course_history:
        sections.append("## COURSE & TOURNAMENT HISTORY\n")
        for name, text in list(course_history.items())[:4]:
            sections.append(f"**{name}:**")
            # Truncate to first 400 chars of each history blurb
            sections.append(text[:400] + ("..." if len(text) > 400 else ""))
            sections.append("")

    # Upcoming
    if upcoming:
        sections.append("## UPCOMING TOURNAMENTS\n")
        for e in upcoming[:2]:
            sections.append(f"- {e.get('name')} ({e.get('date')}) at {e.get('venue', 'TBD')}, {e.get('city', '')}")
        sections.append("")

    # Last week's picks
    if last_picks:
        sections.append("## LAST WEEK'S PICKS (to cross-reference)\n")
        sections.append(f"Tournament: {last_picks.get('tournament')}")
        for pick in last_picks.get("picks", []):
            sections.append(f"- {pick['player']} — result: {pick.get('result', 'pending')}")
        sections.append("")

    return "\n".join(sections)


def slugify(text: str) -> str:
    """Convert title to URL-safe slug."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:60]


def generate_frontmatter(
    tournament_data: dict,
    article_body: str,
    picks: list[str],
) -> str:
    """Generate MDX frontmatter from tournament data and article."""
    today = datetime.date.today().isoformat()
    completed = tournament_data.get("completed_events", [])
    upcoming = tournament_data.get("upcoming_events", [])

    if completed:
        event = completed[0]
        title = f"{event.get('name')}: {today[:4]} in Review"
        tournament = event.get("name", "")
        tour_raw = event.get("tour", "PGA Tour")
        tour = tour_raw if tour_raw in ["PGA Tour", "DP World Tour", "LIV Golf"] else "Other"
        course = event.get("venue", {}).get("name", "")
        winner_name = event.get("winner", {}).get("name", "")
        winner_score = event.get("winner", {}).get("score", "")
        is_major = any(m in tournament.lower() for m in ["masters", "open championship", "u.s. open", "pga championship"])
    else:
        title = f"Golf Week in Review — {today}"
        tournament = "Multiple Events"
        tour = "PGA Tour"
        course = ""
        winner_name = ""
        winner_score = ""
        is_major = False

    # Extract a description (first ~160 chars of article body)
    first_para = article_body.strip().split("\n")[0][:160].strip()
    description = re.sub(r"[#*`]", "", first_para).strip()

    next_event = upcoming[0] if upcoming else {}
    tags_list = ["golf", slugify(tournament)]
    if is_major:
        tags_list.append("major")

    tags_yaml = "[" + ", ".join(f'"{t}"' for t in tags_list) + "]"

    picks_yaml = ""
    if picks:
        picks_yaml = "\npicks:\n" + "\n".join(
            f'  - player: "{p}"\n    result: "pending"' for p in picks
        )

    frontmatter = f"""---
title: "{title}"
description: "{description}"
date: {today}
tournament: "{tournament}"
tour: "{tour}"
course: "{course}"
winner: "{winner_name}"
winnerScore: "{winner_score}"
isMajor: {str(is_major).lower()}
tags: {tags_yaml}{picks_yaml}
nextTournament: "{next_event.get('name', '')}"
nextTournamentDate: "{next_event.get('date', '')}"
nextTournamentCourse: "{next_event.get('venue', '')}"
---"""

    return frontmatter


def extract_picks_from_article(article_body: str) -> list[str]:
    """Pull the 5 picks out of the generated article for picks history tracking."""
    picks = []
    in_picks = False
    for line in article_body.split("\n"):
        if "## Our Picks" in line:
            in_picks = True
            continue
        if in_picks and line.startswith("##"):
            break
        if in_picks:
            # Match "1. **Player Name**" or "**Player Name**"
            match = re.search(r"\*\*([^*]+)\*\*", line)
            if match:
                picks.append(match.group(1).strip())
    return picks[:5]


# ─── Entry point ─────────────────────────────────────────────────────────────

def main():
    print("\n=== Scratch Research Co. — Article Generation ===\n")

    data_file = DATA_DIR / "tournament_data.json"
    if not data_file.exists():
        print("ERROR: data/tournament_data.json not found. Run fetch_data.py first.")
        sys.exit(1)

    tournament_data = json.loads(data_file.read_text())
    picks_history = load_picks_history()

    print("Building prompt from tournament data...")
    user_content = build_user_prompt(tournament_data, picks_history)

    print("Calling Claude API to generate article...")
    article_body = call_claude(
        messages=[{"role": "user", "content": user_content}],
        system=SYSTEM_PROMPT,
    )

    print("Extracting picks for history tracking...")
    picks = extract_picks_from_article(article_body)
    print(f"  Picks found: {picks}")

    print("Generating frontmatter...")
    frontmatter = generate_frontmatter(tournament_data, article_body, picks)

    full_article = frontmatter + "\n\n" + article_body

    # Determine output path
    today = datetime.date.today().isoformat()
    year = today[:4]
    completed = tournament_data.get("completed_events", [])
    slug_source = completed[0].get("name", "golf-week") if completed else "golf-week"
    slug = f"{today}-{slugify(slug_source)}"

    year_dir = ARTICLES_DIR / year
    year_dir.mkdir(parents=True, exist_ok=True)
    output_path = year_dir / f"{slug}.mdx"

    output_path.write_text(full_article)
    print(f"\n✓ Article written to {output_path.relative_to(ROOT)}")

    # Save picks to history
    if picks:
        upcoming = tournament_data.get("upcoming_events", [{}])
        next_tournament = upcoming[0].get("name", "Next Tournament") if upcoming else "Next Tournament"
        save_picks_to_history(next_tournament, today, picks)
        print(f"✓ Picks saved to picks history for {next_tournament}")

    # Write a manifest for the PR creation step
    manifest = {
        "article_path": str(output_path.relative_to(ROOT)),
        "article_slug": slug,
        "tournament": completed[0].get("name", "") if completed else "",
        "winner": completed[0].get("winner", {}).get("name", "") if completed else "",
        "picks": picks,
        "generated_at": tournament_data.get("generated_at", ""),
    }
    manifest_path = DATA_DIR / "generation_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"✓ Manifest written to {manifest_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
