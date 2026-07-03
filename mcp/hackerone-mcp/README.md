# HackerOne MCP

MCP server exposing HackerOne data as tools, plus a standalone CLI for the
authenticated Hacker API.

## Files

| File | Purpose |
|---|---|
| `mcp_server.py` | MCP entrypoint (stdio). Registers all tools below. Run by Claude Code / OpenCode. |
| `server.py` | Public GraphQL functions (no auth) + standalone CLI. Imported by `mcp_server.py`. |
| `h1_hacker_api.py` | Authenticated REST client (`api.hackerone.com/v1/hackers`) + standalone CLI. |
| `config.json` | Copy-me template for `.claude/settings.json` `mcpServers`. |
| `opencode-config.json` | OpenCode MCP registration. |

## Tools

**Public (no credentials):**
`search_disclosed_reports`, `get_program_stats`, `get_program_policy`

**Authenticated (require API credentials):**
`list_my_programs`, `get_program_scope`, `list_my_reports`, `get_report`,
`get_balance`, `get_earnings`, `get_payouts`

**Gated write (only registered when `H1_ENABLE_SUBMIT=1`):**
`submit_report` — performs a real submission. Off by default.

## Credentials

HTTP Basic auth. Username = **API Token identifier**, password = **API Token value**.
Generate at `https://hackerone.com/settings/api_token/edit`.

Loaded in priority order:
1. Env vars `H1_API_USERNAME` / `H1_API_TOKEN`
2. `~/.hackerone/creds.json` — `{"identifier": "...", "token": "..."}`
3. Repo `config.json` `h1_api_token` (token only; needs `H1_API_USERNAME` env)

Never commit credentials. `config.json` is gitignored; `~/.hackerone/creds.json`
lives outside the repo (`chmod 600`).

```bash
mkdir -p ~/.hackerone
printf '{"identifier":"YOUR_ID","token":"YOUR_TOKEN"}' > ~/.hackerone/creds.json
chmod 600 ~/.hackerone/creds.json
```

## Setup

```bash
pip install mcp            # one-time SDK install
python3 mcp/hackerone-mcp/h1_hacker_api.py whoami   # verify auth (lists 1 program)
```

Register with Claude Code — copy the `hackerone` entry from `config.json` into
your `.claude/settings.json` `mcpServers`, then restart Claude Code. To enable
`submit_report`, add `"env": { "H1_ENABLE_SUBMIT": "1" }` to that entry.

## CLI quick reference

```bash
# authenticated
python3 h1_hacker_api.py programs
python3 h1_hacker_api.py scope <handle>
python3 h1_hacker_api.py reports
python3 h1_hacker_api.py balance

# public (no auth)
python3 server.py search "ssrf" --limit 5
python3 server.py stats <handle>
python3 server.py policy <handle>
```
