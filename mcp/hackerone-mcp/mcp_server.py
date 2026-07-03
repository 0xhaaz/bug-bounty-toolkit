#!/usr/bin/env python3
"""
HackerOne MCP server (stdio) — public + authenticated hacker API.

Exposes, as MCP tools:
  Public (no auth, hackerone.com GraphQL):
    - search_disclosed_reports, get_program_stats, get_program_policy
  Authenticated (api.hackerone.com/v1/hackers, HTTP Basic):
    - list_my_programs, get_program_scope, list_my_reports, get_report,
      get_balance, get_earnings, get_payouts
  Gated (only registered when H1_ENABLE_SUBMIT=1):
    - submit_report

Credentials for the authenticated tools come from env or ~/.hackerone/creds.json
(see h1_hacker_api.load_creds). No secrets are read from or written to this repo.

Requires the `mcp` Python SDK:  pip install mcp
Register in .claude/settings.json — see config.json in this directory.
"""

import os
import sys
from pathlib import Path

# Make sibling modules importable regardless of launch cwd.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from mcp.server.fastmcp import FastMCP  # noqa: E402

import server as public  # public GraphQL functions (server.py)  # noqa: E402
import h1_hacker_api as h1  # authenticated REST client  # noqa: E402

mcp = FastMCP("hackerone")


# ─── Public tools (no auth): get_program_stats, get_program_policy ───────────
# (search_disclosed_reports now uses the authenticated Hacktivity REST API —
#  HackerOne removed the public GraphQL field it used to query.)

@mcp.tool()
def search_disclosed_reports(keyword: str = "", program: str = "", limit: int = 10) -> list:
    """Search HackerOne Hacktivity for publicly disclosed reports (requires API creds).

    keyword: freetext search (vuln type, tech), matched server-side.
    program: H1 handle — filtered client-side (best-effort for rare disclosers).
    limit: 1-25. Results include severity, awarded amount, CWE, and CVE ids.
    """
    return h1.search_hacktivity(keyword=keyword, program=program, limit=limit)


@mcp.tool()
def get_program_stats(program: str) -> dict:
    """Public stats for a program handle: bounty ranges, resolved counts, state."""
    return public.get_program_stats(program)


@mcp.tool()
def get_program_policy(program: str) -> dict:
    """Public policy + structured scope for a program handle (safe harbor, scope)."""
    return public.get_program_policy(program)


# ─── Authenticated tools (require API creds) ─────────────────────────────────

@mcp.tool()
def list_my_programs(max_items: int = 100) -> list:
    """Programs the authenticated hacker can access (handle, name, state, bounties)."""
    return h1.list_my_programs(max_items=max_items)


@mcp.tool()
def get_program_scope(handle: str, max_items: int = 200) -> list:
    """Authenticated structured scopes for a program: in-scope assets + bounty eligibility."""
    return h1.get_program_scope(handle, max_items=max_items)


@mcp.tool()
def list_my_reports(max_items: int = 50) -> list:
    """The authenticated hacker's own submitted reports (id, title, state, created_at)."""
    return h1.list_my_reports(max_items=max_items)


@mcp.tool()
def get_report(report_id: str) -> dict:
    """Full detail for one of the hacker's reports by id."""
    return h1.get_report(report_id)


@mcp.tool()
def get_balance() -> dict:
    """Current HackerOne payments balance for the authenticated hacker."""
    return h1.get_balance()


@mcp.tool()
def get_earnings(max_items: int = 50) -> list:
    """Earnings history for the authenticated hacker."""
    return h1.get_earnings(max_items=max_items)


@mcp.tool()
def get_payouts(max_items: int = 50) -> list:
    """Payout history for the authenticated hacker."""
    return h1.get_payouts(max_items=max_items)


# ─── Gated write tool (opt-in only) ──────────────────────────────────────────

if os.environ.get("H1_ENABLE_SUBMIT") == "1":
    @mcp.tool()
    def submit_report(team_handle: str, title: str, vulnerability_information: str,
                      impact: str, severity_rating: str = "", weakness_id: int = 0,
                      structured_scope_id: str = "") -> dict:
        """Submit a live report to a program. ONLY available when H1_ENABLE_SUBMIT=1.

        This performs a real submission. Double-check scope and content first.
        """
        return h1.submit_report(
            team_handle=team_handle, title=title,
            vulnerability_information=vulnerability_information, impact=impact,
            severity_rating=severity_rating or None,
            weakness_id=weakness_id or None,
            structured_scope_id=structured_scope_id or None,
            confirm=True,
        )


if __name__ == "__main__":
    mcp.run()
