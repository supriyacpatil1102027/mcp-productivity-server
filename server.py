"""
MCP Server: Personal Productivity Assistant
Domain: Personal Productivity (task tracking + email reminders)
Author: Supriya Patil (scp232@cornell.edu)

Structure adapted from the MCP Python SDK quickstart example:
https://github.com/modelcontextprotocol/python-sdk
"""

import os
import re
import sqlite3
import smtplib
import time
from email.mime.text import MIMEText
from pathlib import Path
from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

# Secret management: credentials live in a local .env file (never committed --
# see .gitignore), loaded via pathlib relative to this file so it works
# regardless of the process's working directory.
load_dotenv(Path(__file__).parent / ".env")

mcp = MCPServer("productivity-server")
DB_PATH = Path(__file__).parent / "tasks.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            due_date TEXT,
            priority TEXT
        )
    """)
    return conn


# ---------- Best Practice 1: Input Sanitization ----------
TITLE_MAX_LEN = 200
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ALLOWED_PRIORITIES = {"low", "medium", "high"}


def sanitize_title(title: str) -> str:
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Task title must be a non-empty string.")
    title = title.strip()
    if len(title) > TITLE_MAX_LEN:
        raise ValueError(f"Task title must be under {TITLE_MAX_LEN} characters.")
    if re.search(r"[;<>`$]", title):  # blocklist common injection/shell chars
        raise ValueError("Task title contains disallowed characters.")
    return title


def sanitize_date(due_date: str) -> str:
    if not DATE_RE.match(due_date):
        raise ValueError("due_date must be in YYYY-MM-DD format.")
    return due_date


def sanitize_priority(priority: str) -> str:
    priority = priority.lower().strip()
    if priority not in ALLOWED_PRIORITIES:
        raise ValueError("priority must be one of: low, medium, high.")
    return priority


EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def sanitize_email_address(email: str) -> str:
    email = email.strip()
    # Reject embedded CR/LF up front -- email.message headers do not strip
    # them, so an unsanitized value could inject extra headers (e.g. Bcc:).
    if "\r" in email or "\n" in email or not EMAIL_RE.match(email):
        raise ValueError("recipient_email is not a valid email address.")
    return email


def sanitize_header_value(value: str, field_name: str) -> str:
    if "\r" in value or "\n" in value:
        raise ValueError(f"{field_name} must not contain newline characters.")
    return value


@mcp.tool()
def add_task(title: str, due_date: str, priority: str = "medium") -> dict:
    """Add a task to the tracker. due_date format: YYYY-MM-DD."""
    try:
        title = sanitize_title(title)
        due_date = sanitize_date(due_date)
        priority = sanitize_priority(priority)
    except ValueError as e:
        return {"success": False, "error": str(e)}  # safe: only validation msg leaks

    conn = get_db()
    # Parameterized query -- prevents SQL injection no matter what's in title
    conn.execute(
        "INSERT INTO tasks (title, due_date, priority) VALUES (?, ?, ?)",
        (title, due_date, priority),
    )
    conn.commit()
    conn.close()
    return {"success": True, "message": f"Task '{title}' added for {due_date}."}


@mcp.tool()
def list_tasks() -> dict:
    """List all tracked tasks."""
    conn = get_db()
    rows = conn.execute("SELECT title, due_date, priority FROM tasks ORDER BY due_date").fetchall()
    conn.close()
    return {"tasks": [{"title": t, "due_date": d, "priority": p} for t, d, p in rows]}


# ---------- Best Practice 2: Rate Limiting ----------
_email_calls = []  # timestamps of recent calls
RATE_LIMIT = 3       # max calls
RATE_WINDOW = 60      # seconds


def check_rate_limit():
    now = time.time()
    while _email_calls and now - _email_calls[0] > RATE_WINDOW:
        _email_calls.pop(0)
    if len(_email_calls) >= RATE_LIMIT:
        raise RuntimeError(f"Rate limit exceeded: max {RATE_LIMIT} emails per {RATE_WINDOW}s.")
    _email_calls.append(now)


@mcp.tool()
def send_task_reminder_email(recipient_email: str, subject: str, body: str) -> dict:
    """Send a task reminder email. Requires GMAIL_USER / GMAIL_APP_PASSWORD env vars."""
    try:
        recipient_email = sanitize_email_address(recipient_email)
        subject = sanitize_header_value(subject, "subject")
        check_rate_limit()
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except RuntimeError as e:
        return {"success": False, "error": str(e)}

    gmail_user = os.environ.get("GMAIL_USER")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD")
    if not gmail_user or not gmail_pass:
        return {"success": False, "error": "Email credentials are not configured."}

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = recipient_email

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, [recipient_email], msg.as_string())
        return {"success": True, "message": f"Reminder sent to {recipient_email}."}
    except Exception:
        # Error Disclosure: never return the raw SMTP exception/stack trace to the caller
        return {"success": False, "error": "Failed to send email. Check server logs."}


@mcp.prompt()
def daily_planning_prompt() -> str:
    """Generate a prompt that summarizes today's tasks for planning."""
    conn = get_db()
    rows = conn.execute("SELECT title, due_date, priority FROM tasks ORDER BY due_date").fetchall()
    conn.close()
    if not rows:
        return "I have no tasks tracked yet. Help me think through what I should add for today."
    lines = "\n".join(f"- {t} (due {d}, priority: {p})" for t, d, p in rows)
    return f"Here are my current tasks:\n{lines}\n\nHelp me prioritize today's plan."


if __name__ == "__main__":
    mcp.run()
