#!/usr/bin/env python3
"""
HackerOne Hacker API client — authenticated endpoints (api.hackerone.com/v1/hackers).

Auth: HTTP Basic. Username = API Token identifier, password = API Token value.
Docs: https://api.hackerone.com/hacker-resources/

Credentials are loaded, in priority order, from:
  1. Env vars  H1_API_USERNAME / H1_API_TOKEN
  2. ~/.hackerone/creds.json   {"identifier": "...", "token": "..."}
  3. <repo>/config.json        {"h1_api_token": "..."}  (token only; needs H1_API_USERNAME env)

Never commit credentials. creds.json lives outside the repo; config.json is gitignored.

Usage (standalone test):
    python3 h1_hacker_api.py setup          # interactive: prompts for identifier + hidden token
    python3 h1_hacker_api.py programs
    python3 h1_hacker_api.py scope <handle>
    python3 h1_hacker_api.py reports
    python3 h1_hacker_api.py report <id>
    python3 h1_hacker_api.py balance
    python3 h1_hacker_api.py earnings
    python3 h1_hacker_api.py payouts
    python3 h1_hacker_api.py whoami       # cheap auth probe (lists 1 program)
"""

import base64
import getpass
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# ─── SSL context ─────────────────────────────────────────────────────────────
_SSL_CTX = ssl.create_default_context()
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    pass  # fall back to system trust store; do NOT disable verification

API_BASE = "https://api.hackerone.com/v1/hackers"
DEFAULT_TIMEOUT = 20
MAX_RETRIES = 3
USER_AGENT = "claude-bug-bounty/2.1 (+h1-hacker-api)"

CREDS_FILE = Path.home() / ".hackerone" / "creds.json"
# repo root = two levels up from this file (mcp/hackerone-mcp/ -> repo/)
REPO_ROOT = Path(__file__).resolve().parents[2]
REPO_CONFIG = REPO_ROOT / "config.json"


class H1AuthError(Exception):
    """Missing or malformed credentials."""


class H1APIError(Exception):
    """API request failed."""
    def __init__(self, message, status_code=None, body=None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


# ─── Credentials ─────────────────────────────────────────────────────────────

def load_creds() -> tuple[str, str]:
    """Return (identifier, token). Raise H1AuthError if unresolved."""
    ident = os.environ.get("H1_API_USERNAME")
    token = os.environ.get("H1_API_TOKEN")
    if ident and token:
        return ident, token

    if CREDS_FILE.exists():
        try:
            data = json.loads(CREDS_FILE.read_text())
        except (json.JSONDecodeError, OSError) as e:
            raise H1AuthError(f"Cannot read {CREDS_FILE}: {e}")
        ident = ident or data.get("identifier") or data.get("username")
        token = token or data.get("token")
        if ident and token:
            return ident, token

    # last resort: token from gitignored repo config, identifier from env
    if not token and REPO_CONFIG.exists():
        try:
            cfg = json.loads(REPO_CONFIG.read_text())
            token = cfg.get("h1_api_token")
        except (json.JSONDecodeError, OSError):
            pass

    if ident and token:
        return ident, token

    raise H1AuthError(
        "HackerOne API credentials not found. Provide them via env "
        "(H1_API_USERNAME, H1_API_TOKEN) or ~/.hackerone/creds.json "
        '({"identifier": "...", "token": "..."}).'
    )


def _auth_header() -> str:
    ident, token = load_creds()
    raw = f"{ident}:{token}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def setup_creds() -> None:
    """Interactively write ~/.hackerone/creds.json. Token is entered hidden."""
    existing = {}
    if CREDS_FILE.exists():
        try:
            existing = json.loads(CREDS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    default_id = existing.get("identifier") or os.environ.get("H1_API_USERNAME") or ""
    prompt = f"HackerOne API identifier [{default_id}]: " if default_id else "HackerOne API identifier: "
    ident = input(prompt).strip() or default_id
    if not ident:
        print("No identifier entered — aborted.")
        sys.exit(1)
    token = getpass.getpass("HackerOne API token (hidden — paste then Enter): ").strip()
    if not token:
        print("No token entered — aborted.")
        sys.exit(1)
    CREDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CREDS_FILE.write_text(json.dumps({"identifier": ident, "token": token}))
    CREDS_FILE.chmod(0o600)
    print(f"Saved {CREDS_FILE} (chmod 600). identifier={ident!r}, token=***{len(token)} chars hidden***")


# ─── HTTP ────────────────────────────────────────────────────────────────────

def _request(method: str, path: str, params: dict = None, body: dict = None,
             timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Signed request to the hacker API with retry on 429/5xx."""
    url = API_BASE + path
    if params:
        # drop None values, then urlencode (supports page[number] style keys)
        clean = {k: v for k, v in params.items() if v is not None}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)

    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {
        "Authorization": _auth_header(),
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    if data is not None:
        headers["Content-Type"] = "application/json"

    last_err = None
    for attempt in range(MAX_RETRIES):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            if e.code == 429 or 500 <= e.code < 600:
                retry_after = e.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.isdigit() else (2 ** attempt)
                last_err = H1APIError(f"HTTP {e.code}: {e.reason}", e.code, err_body)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(min(wait, 30))
                    continue
            # 401/403/404 etc — no retry
            hint = ""
            if e.code == 401:
                hint = (" (check identifier/token — the Basic-auth username must be "
                        "the API Token identifier, not necessarily your handle)")
            raise H1APIError(f"HTTP {e.code}: {e.reason}{hint}", e.code, err_body)
        except urllib.error.URLError as e:
            last_err = H1APIError(f"Network error: {e.reason}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
        except json.JSONDecodeError as e:
            raise H1APIError(f"Invalid JSON response: {e}")
    raise last_err or H1APIError("Request failed after retries")


def _paginate(path: str, params: dict = None, max_items: int = 100) -> list[dict]:
    """Follow JSON:API pagination up to max_items."""
    params = dict(params or {})
    params.setdefault("page[size]", 100)
    out = []
    page = 1
    while len(out) < max_items:
        params["page[number]"] = page
        resp = _request("GET", path, params=params)
        batch = resp.get("data", [])
        if not batch:
            break
        out.extend(batch)
        if not (resp.get("links") or {}).get("next"):
            break
        page += 1
    return out[:max_items]


# ─── Endpoints ───────────────────────────────────────────────────────────────

def list_my_programs(max_items: int = 100) -> list[dict]:
    """Programs the authenticated hacker can access."""
    items = _paginate("/programs", max_items=max_items)
    return [{
        "handle": (i.get("attributes") or {}).get("handle"),
        "name": (i.get("attributes") or {}).get("name"),
        "state": (i.get("attributes") or {}).get("state"),
        "submission_state": (i.get("attributes") or {}).get("submission_state"),
        "offers_bounties": (i.get("attributes") or {}).get("offers_bounties"),
        "id": i.get("id"),
    } for i in items]


def get_program_scope(handle: str, max_items: int = 200) -> list[dict]:
    """Structured scopes (in-scope assets) for a program handle."""
    if not handle:
        raise ValueError("handle required")
    items = _paginate(f"/programs/{urllib.parse.quote(handle)}/structured_scopes",
                      max_items=max_items)
    return [{
        "asset_type": (i.get("attributes") or {}).get("asset_type"),
        "asset_identifier": (i.get("attributes") or {}).get("asset_identifier"),
        "eligible_for_bounty": (i.get("attributes") or {}).get("eligible_for_bounty"),
        "eligible_for_submission": (i.get("attributes") or {}).get("eligible_for_submission"),
        "max_severity": (i.get("attributes") or {}).get("max_severity"),
        "instruction": (i.get("attributes") or {}).get("instruction"),
        "id": i.get("id"),
    } for i in items]


def list_my_reports(max_items: int = 50) -> list[dict]:
    """The authenticated hacker's own reports."""
    items = _paginate("/me/reports", max_items=max_items)
    return [{
        "id": i.get("id"),
        "title": (i.get("attributes") or {}).get("title"),
        "state": (i.get("attributes") or {}).get("state"),
        "created_at": (i.get("attributes") or {}).get("created_at"),
    } for i in items]


def get_report(report_id: str) -> dict:
    """Full detail for one report."""
    if not report_id:
        raise ValueError("report_id required")
    resp = _request("GET", f"/reports/{urllib.parse.quote(str(report_id))}")
    return resp.get("data", resp)


def get_balance() -> dict:
    return _request("GET", "/payments/balance").get("data", {})


def get_earnings(max_items: int = 50) -> list[dict]:
    return _paginate("/payments/earnings", max_items=max_items)


def get_payouts(max_items: int = 50) -> list[dict]:
    return _paginate("/payments/payouts", max_items=max_items)


def submit_report(team_handle: str, title: str, vulnerability_information: str,
                  impact: str, severity_rating: str = None,
                  weakness_id: int = None, structured_scope_id: str = None,
                  confirm: bool = False) -> dict:
    """Submit a report. GATED: requires confirm=True AND H1_ENABLE_SUBMIT=1."""
    if not confirm or os.environ.get("H1_ENABLE_SUBMIT") != "1":
        raise H1APIError(
            "submit_report is disabled. Set H1_ENABLE_SUBMIT=1 and pass confirm=True "
            "to allow a live submission."
        )
    for name, val in [("team_handle", team_handle), ("title", title),
                      ("vulnerability_information", vulnerability_information),
                      ("impact", impact)]:
        if not val:
            raise ValueError(f"{name} required")
    attrs = {
        "team_handle": team_handle,
        "title": title,
        "vulnerability_information": vulnerability_information,
        "impact": impact,
    }
    if severity_rating:
        attrs["severity_rating"] = severity_rating
    if weakness_id:
        attrs["weakness_id"] = weakness_id
    if structured_scope_id:
        attrs["structured_scope_id"] = structured_scope_id
    body = {"data": {"type": "report", "attributes": attrs}}
    return _request("POST", "/reports", body=body).get("data", {})


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    arg = sys.argv[2] if len(sys.argv) > 2 else None
    if cmd == "setup":
        setup_creds()
        return
    try:
        if cmd == "programs":
            out = list_my_programs()
        elif cmd == "whoami":
            progs = list_my_programs(max_items=1)
            out = {"authenticated": True,
                   "identifier": load_creds()[0],
                   "sample_program": progs[0] if progs else None}
        elif cmd == "scope":
            out = get_program_scope(arg)
        elif cmd == "reports":
            out = list_my_reports()
        elif cmd == "report":
            out = get_report(arg)
        elif cmd == "balance":
            out = get_balance()
        elif cmd == "earnings":
            out = get_earnings()
        elif cmd == "payouts":
            out = get_payouts()
        else:
            print(f"Unknown command: {cmd}")
            sys.exit(1)
        print(json.dumps(out, indent=2))
    except (H1AuthError, H1APIError, ValueError) as e:
        payload = {"error": str(e)}
        if isinstance(e, H1APIError):
            payload["status_code"] = e.status_code
            if e.body:
                payload["body"] = e.body[:500]
        print(json.dumps(payload, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
