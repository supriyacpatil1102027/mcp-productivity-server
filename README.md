# Productivity MCP Server

An MCP (Model Context Protocol) server implementing a **Personal Productivity** domain: task
tracking with SQLite storage and email reminders via Gmail SMTP.

## Tools
- `add_task(title, due_date, priority)` — add a task (validates/sanitizes all inputs, stores via parameterized SQL)
- `list_tasks()` — list all tracked tasks
- `send_task_reminder_email(recipient_email, subject, body)` — sends an email reminder (rate-limited, requires Gmail app-password auth)

## Prompt
- `daily_planning_prompt()` — builds a planning prompt from your current task list

## Best Practices Implemented
1. **Input Sanitization** — `add_task` validates title length/characters, date format (YYYY-MM-DD),
   and priority against an allow-list, and always writes to SQLite via parameterized queries
   (never string-concatenated SQL). See `exploit_tests.py` Exploit 1 for a blocked SQL-injection attempt.
2. **Rate Limiting** — `send_task_reminder_email` allows at most 3 calls per 60-second window
   (in-memory sliding window). See `exploit_tests.py` Exploit 2 for a blocked rapid-fire attempt.

Bonus: errors returned to the client are always generic/validation-level messages — raw
exceptions (e.g. SMTP stack traces) are never disclosed (Error Disclosure best practice).

## Authentication
Email sending requires a **Gmail App Password** (not your real Gmail password):
Google Account -> Security -> 2-Step Verification -> App passwords -> generate one for "Mail".
Credentials are passed as environment variables (`GMAIL_USER`, `GMAIL_APP_PASSWORD`) via the
Claude Desktop MCP config — never hardcoded in source.

## Setup

```bash
# from this project folder
uv sync
```

Test the tools directly:
```bash
uv run python exploit_tests.py
```

Run the server standalone (for debugging):
```bash
uv run server.py
```

## Claude Desktop Configuration
See `claude_desktop_config.example.json`. Copy its contents into your Claude Desktop config file
(Claude menu -> Settings -> Developer -> Edit Config), update the `--directory` path and Gmail
credentials, then restart Claude Desktop.

## Architecture
See `architecture-diagram.mmd` (open at https://mermaid.live to view/export as an image).

```
Claude Desktop <--stdio--> productivity-server
                              |-- add_task ---------> tasks.db (SQLite)
                              |-- list_tasks -------> tasks.db (SQLite)
                              |-- send_task_reminder_email --> Gmail SMTP
                              |-- daily_planning_prompt ------> tasks.db (SQLite)
```

## Credits
Server structure adapted from the official MCP Python SDK quickstart:
https://github.com/modelcontextprotocol/python-sdk
