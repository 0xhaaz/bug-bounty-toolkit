#!/usr/bin/env python3
"""
practice.py — Session journal for bug bounty hunting.

Tracks what you tested, on which target, and what you learned.
Session files are flat markdown in sessions/YYYY-MM-DD-<target>.md.

Usage:
  python3 tools/practice.py start --target <handle>
  python3 tools/practice.py note <message>
  python3 tools/practice.py review [--days N]
"""

import argparse
import json
import os
import re
import subprocess
import sys
import textwrap
from datetime import datetime, timedelta

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SESSIONS_DIR = os.path.join(_REPO, "sessions")
MCP_SCRIPT = os.path.join(_REPO, "mcp", "hackerone-mcp", "server.py")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _now() -> str:
    return datetime.now().strftime("%H:%M")


def _find_today_session(target: str = "") -> str | None:
    """Find a session file for today, optionally matching target."""
    prefix = _today()
    if not os.path.isdir(SESSIONS_DIR):
        return None
    candidates = []
    for f in os.listdir(SESSIONS_DIR):
        if not f.endswith(".md") or not f.startswith(prefix):
            continue
        if target and target not in f:
            continue
        candidates.append(os.path.join(SESSIONS_DIR, f))
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


def _fetch_disclosed_reports(target: str) -> str:
    """Fetch disclosed reports for a target via H1 MCP. Returns markdown."""
    if not os.path.exists(MCP_SCRIPT):
        return "_MCP not available_\n"
    try:
        result = subprocess.run(
            ["python3", MCP_SCRIPT, "search", "", "--program", target, "--limit", 5],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return "_MCP search failed_\n"
        reports = json.loads(result.stdout)
        if not reports:
            return "_No disclosed reports found_\n"
        lines = []
        for r in reports:
            date = r.get("disclosed_at", "?")[:10]
            sev = r.get("severity", "?")
            title = r.get("title", "?")
            lines.append(f"- {date} [{sev}] {title}")
        return "\n".join(lines) + "\n"
    except Exception:
        return "_MCP error_\n"


def cmd_start(args: argparse.Namespace) -> int:
    """Create or open a session file for today."""
    target = args.target

    if not re.match(r'^[a-zA-Z0-9._-]+$', target):
        print("Error: target must be alphanumeric, dots, dashes, or underscores only")
        return 1

    # Check if already exists
    existing = _find_today_session(target)
    if existing:
        print(f"Session already exists: {existing}")
        return 0

    # Create sessions/ if missing
    os.makedirs(SESSIONS_DIR, exist_ok=True)

    # Fetch intel
    print(f"Fetching disclosed reports for {target}...")
    reports = _fetch_disclosed_reports(target)

    # Write session file
    filepath = os.path.join(SESSIONS_DIR, f"{_today()}-{target}.md")
    content = textwrap.dedent(f"""\
    # Session: {_today()} — {target}

    ## Disclosed Reports
    {reports}
    ## Hunt Log

    ## Lessons Learned

    """)
    with open(filepath, "w") as f:
        f.write(content)

    print(f"Session created: {filepath}")
    return 0


def cmd_note(args: argparse.Namespace) -> int:
    """Append a timestamped note to today's session."""
    message = args.message
    if not message:
        print("Error: message is required")
        return 1

    session = _find_today_session(target=args.target)
    if not session:
        # Create an unsorted session
        os.makedirs(SESSIONS_DIR, exist_ok=True)
        session = os.path.join(SESSIONS_DIR, f"{_today()}-unsorted.md")
        with open(session, "w") as f:
            f.write(f"# Session: {_today()} — unsorted\n\n## Hunt Log\n\n## Lessons Learned\n\n")
        print(f"Created new session: {session}")

    timestamp = _now()
    line = f"[{timestamp}] {message}\n"
    with open(session, "a") as f:
        f.write(line)
    print(f"Logged to {os.path.basename(session)}: {line.strip()}")
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    """Aggregate recent sessions into a review."""
    days = args.days
    cutoff = datetime.now() - timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    if not os.path.isdir(SESSIONS_DIR):
        print("No sessions directory found.")
        return 0

    sessions: list[str] = []
    for f in os.listdir(SESSIONS_DIR):
        if not f.endswith(".md"):
            continue
        # Compare date portion of filename (YYYY-MM-DD)
        file_date = f[:10]
        if file_date < cutoff_str:
            continue
        sessions.append(os.path.join(SESSIONS_DIR, f))

    if not sessions:
        print(f"No sessions in the last {days} days.")
        return 0

    sessions.sort()
    print(f"\n{'='*60}")
    print(f"  Review: Last {days} Days ({len(sessions)} sessions)")
    print(f"{'='*60}\n")

    target_sessions: dict[str, list[str]] = {}
    for sp in sessions:
        fname = os.path.basename(sp)
        # Extract target from filename: YYYY-MM-DD-<target>.md
        parts = fname.replace(".md", "").split("-", 3)
        target = parts[3] if len(parts) > 3 else "unknown"
        target_sessions.setdefault(target, []).append(sp)

    for target, sfiles in sorted(target_sessions.items()):
        print(f"  ── {target} ({len(sfiles)} sessions) ──")
        for sp in sfiles:
            with open(sp) as f:
                content = f.read()
            # Extract Hunt Log lines
            in_log = False
            in_lessons = False
            log_lines: list[str] = []
            lessons_lines: list[str] = []
            for line in content.splitlines():
                if line.strip().startswith("## Hunt Log"):
                    in_log = True
                    in_lessons = False
                    continue
                if line.strip().startswith("## Lessons Learned"):
                    in_log = False
                    in_lessons = True
                    continue
                if line.strip().startswith("## "):
                    in_log = False
                    in_lessons = False
                if in_log and line.strip():
                    log_lines.append(f"    {line.strip()}")
                if in_lessons and line.strip():
                    lessons_lines.append(f"    {line.strip()}")
            if log_lines:
                print(f"    {os.path.basename(sp)}:")
                for l in log_lines:
                    print(l)
            if lessons_lines:
                print(f"    Lessons:")
                for l in lessons_lines:
                    print(l)
            print()

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Bug bounty session journal",
    )
    sub = parser.add_subparsers(dest="command", help="Subcommand")

    # start
    p_start = sub.add_parser("start", help="Start a new session for a target")
    p_start.add_argument("--target", "-t", type=str, required=True, help="H1 program handle")
    p_start.set_defaults(func=cmd_start)

    # note
    p_note = sub.add_parser("note", help="Log a note to today's session")
    p_note.add_argument("message", type=str, help="What you tested or found")
    p_note.add_argument("--target", "-t", type=str, default="", help="Target handle (default: most recent session)")
    p_note.set_defaults(func=cmd_note)

    # review
    p_review = sub.add_parser("review", help="Review recent sessions")
    p_review.add_argument("--days", type=int, default=7, help="Number of days to review")
    p_review.set_defaults(func=cmd_review)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
