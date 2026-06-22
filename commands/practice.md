---
description: Session journal for bug bounty hunting. Wraps tools/practice.py. Log what you test, on which target, and what you learn. Usage: /practice start --target robinhood
---

# /practice

Track what you test across sessions. Prevents re-testing the same endpoints.

## Commands

### Start a session

```
/practice start --target <handle>
```

Creates a dated journal file in `sessions/`, fetches disclosed reports for that program via H1 MCP.

### Log a note

```
/practice note "tested /api/v2/orders for IDOR — 403, tried tampering → 200 empty"
```

Appends `[HH:MM] <message>` to today's active session file.

### Review recent sessions

```
/practice review [--days 7]
```

Aggregates recent session files. Shows what you tested per target and lessons learned.

## Workflow

1. At session start: `/practice start --target <handle>`
2. During hunt: `/practice note "tested X — result"` after each endpoint
3. Before next session: `/practice review` to see what's been tested
4. After finding something: `/remember` (existing command) to save to pattern_db

## Implementation

All commands delegate to `tools/practice.py`. Session files are stored as plain markdown in `sessions/`.

## Why

- Without a journal, you re-test the same endpoints next session
- The review gives you a weekly retrospective on what's working
- Lessons learned section builds your personal methodology over time
