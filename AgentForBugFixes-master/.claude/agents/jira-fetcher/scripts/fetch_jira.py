#!/usr/bin/env python3
"""
fetch_jira.py — Fetch a Jira ticket and write .bug-fix-state.json
Usage: python3 fetch_jira.py <TICKET_ID_OR_URL>
"""

import sys
import os
import json
import re
import urllib.parse
from pathlib import Path

try:
    import requests
    from dotenv import load_dotenv
except ImportError:
    print("ERROR: Missing dependencies. Run: pip install -r .claude/agents/requirements.txt")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Load environment
# ---------------------------------------------------------------------------
# Walk up from cwd to find .env (handles running from any subdirectory)
_cwd = Path.cwd()
for _parent in [_cwd] + list(_cwd.parents):
    _env_file = _parent / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
        break

JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "").rstrip("/")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")

STATE_FILE = Path(".bug-fix-state.json")
ATTACHMENTS_DIR = Path(".tmp/attachments")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def validate_env() -> None:
    # Jira DC only requires JIRA_BASE_URL + JIRA_API_TOKEN (PAT). Email is optional.
    missing = [k for k, v in {
        "JIRA_BASE_URL": JIRA_BASE_URL,
        "JIRA_API_TOKEN": JIRA_API_TOKEN,
    }.items() if not v]
    if missing:
        print(f"ERROR: Missing environment variables: {', '.join(missing)}")
        print("Copy .env.example to .env and fill in your Jira credentials.")
        sys.exit(1)


def parse_ticket_id(arg: str) -> str:
    """Accept either a ticket ID like PROJ-456 or a full Atlassian URL."""
    # Full URL: extract the issue key from /browse/PROJ-456 or query param
    if arg.startswith("http"):
        parsed = urllib.parse.urlparse(arg)
        # Path style: /browse/PROJ-456
        m = re.search(r"/browse/([A-Z][A-Z0-9_]+-\d+)", parsed.path)
        if m:
            return m.group(1)
        # Query style: ?selectedIssue=PROJ-456
        qs = urllib.parse.parse_qs(parsed.query)
        for key in ("selectedIssue", "issue"):
            if key in qs:
                return qs[key][0]
        print(f"ERROR: Could not extract ticket ID from URL: {arg}")
        sys.exit(1)
    # Plain ticket ID
    if re.match(r"^[A-Z][A-Z0-9_]+-\d+$", arg):
        return arg
    print(f"ERROR: '{arg}' is not a valid Jira ticket ID or URL.")
    sys.exit(1)


def auth_headers() -> dict:
    # Jira Data Center: Bearer auth with a Personal Access Token.
    return {
        "Authorization": f"Bearer {JIRA_API_TOKEN}",
        "Accept": "application/json",
    }


def api_get(path: str, params: dict = None) -> dict:
    # Jira Server/DC uses /rest/api/2/ (Cloud uses /rest/api/3/).
    url = f"{JIRA_BASE_URL}/rest/api/2/{path.lstrip('/')}"
    resp = requests.get(url, headers=auth_headers(), params=params or {}, timeout=30)
    if resp.status_code == 401:
        print("ERROR: Authentication failed. Check JIRA_API_TOKEN (PAT).")
        sys.exit(1)
    if resp.status_code == 404:
        print(f"ERROR: Ticket not found at {url}")
        sys.exit(1)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# ADF flattening
# ---------------------------------------------------------------------------

def flatten_adf(node, _depth=0) -> str:
    """Recursively convert an Atlassian Document Format node to plain text."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node

    node_type = node.get("type", "")
    text_parts = []

    # Leaf text node
    if node_type == "text":
        text = node.get("text", "")
        marks = {m["type"] for m in node.get("marks", [])}
        if "code" in marks:
            text = f"`{text}`"
        return text

    # Code block
    if node_type == "codeBlock":
        inner = "".join(flatten_adf(c) for c in node.get("content", []))
        lang = node.get("attrs", {}).get("language", "")
        return f"\nCODE ({lang}):\n{inner}\n"

    # Mention
    if node_type == "mention":
        return node.get("attrs", {}).get("text", "@unknown")

    # Inline card / link
    if node_type in ("inlineCard", "blockCard"):
        return node.get("attrs", {}).get("url", "")

    # Recurse into content
    for child in node.get("content", []):
        text_parts.append(flatten_adf(child, _depth + 1))

    joined = "".join(text_parts)

    # Block-level spacing
    if node_type in ("paragraph", "heading", "blockquote", "listItem"):
        joined = joined.strip() + "\n"
    elif node_type in ("bulletList", "orderedList"):
        joined = joined + "\n"
    elif node_type == "rule":
        joined = "\n---\n"

    return joined


def safe_flatten(description_field) -> str:
    """Handle both ADF dicts and legacy plain strings."""
    if description_field is None:
        return ""
    if isinstance(description_field, str):
        return description_field
    if isinstance(description_field, dict):
        return flatten_adf(description_field).strip()
    return str(description_field)


# ---------------------------------------------------------------------------
# Bug report section extraction
# ---------------------------------------------------------------------------

# Canonical section names we look for in the description. Each entry is the
# state-key it maps to + a list of accepted heading variants (case-insensitive).
SECTION_MAP = [
    ("reproduction_steps",   ["reproduction steps", "steps to reproduce", "repro steps", "how to reproduce"]),
    ("current_behavior",     ["current behavior", "current behaviour", "current bug"]),
    ("expected_behavior",    ["expected behavior", "expected behaviour"]),
    ("actual_result",        ["actual result", "actual results"]),
    ("expected_result",      ["expected result", "expected results"]),
    ("acceptance_criteria",  ["acceptance criteria", "acceptance criterion"]),
]


def parse_bug_report_sections(description: str) -> dict:
    """
    Parse a Jira description for bold-headed sections like:
        *Current Behavior*
        ...content...
        *Expected Behavior:*
        ...content...

    Returns a dict mapping our canonical state keys (current_behavior, etc.)
    to the trimmed content under each heading. Missing sections are returned
    as empty strings so the state shape is stable.
    """
    result = {state_key: "" for state_key, _ in SECTION_MAP}
    if not description:
        return result

    # Match lines that are ONLY a Jira-style bold heading: optional whitespace
    # then *Heading Name* (with optional trailing colon) then end of line.
    # Group 1 = the heading text without the asterisks.
    heading_re = re.compile(r"(?im)^\s*\*([^*\n]{2,80}?):?\*\s*:?\s*$")

    matches = list(heading_re.finditer(description))
    if not matches:
        return result

    for i, m in enumerate(matches):
        heading_text = m.group(1).strip().lower().rstrip(":").strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(description)
        body = description[body_start:body_end].strip()

        for state_key, variants in SECTION_MAP:
            if heading_text in variants and not result[state_key]:
                result[state_key] = body
                break

    return result


def print_bug_report_summary(state: dict) -> None:
    """Print the structured bug-report sections so the human (and the
    next workflow step) can see them at a glance."""
    print("\n" + "=" * 70)
    print(f"BUG REPORT SECTIONS (from description)")
    print("=" * 70)
    labels = {
        "reproduction_steps":  "Reproduction Steps",
        "current_behavior":    "Current Behavior",
        "expected_behavior":   "Expected Behavior",
        "actual_result":       "Actual Result",
        "expected_result":     "Expected Result",
        "acceptance_criteria": "Acceptance Criteria",
    }
    any_found = False
    for key, label in labels.items():
        body = state.get(key, "").strip()
        if not body:
            continue
        any_found = True
        print(f"\n--- {label} ---")
        print(body)

    if not any_found:
        print("\n(no structured sections detected in the description)")
        print("Full description follows below — read it manually before reproducing.")
        print("\n" + state.get("description", ""))
    print("\n" + "=" * 70)


# ---------------------------------------------------------------------------
# Attachment download
# ---------------------------------------------------------------------------

def download_attachments(ticket_id: str, attachments_raw: list) -> list:
    result = []
    if not attachments_raw:
        return result

    dest_dir = ATTACHMENTS_DIR / ticket_id
    dest_dir.mkdir(parents=True, exist_ok=True)

    for att in attachments_raw:
        filename = att.get("filename", "unknown")
        content_url = att.get("content", "")
        local_path = str(dest_dir / filename)

        try:
            resp = requests.get(content_url, headers=auth_headers(), timeout=60, stream=True)
            resp.raise_for_status()
            with open(local_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=8192):
                    fh.write(chunk)
            print(f"  Downloaded attachment: {filename} → {local_path}")
        except Exception as exc:
            print(f"  WARNING: Could not download attachment '{filename}': {exc}")
            local_path = None

        result.append({
            "filename": filename,
            "url": content_url,
            "local_path": local_path,
        })

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def fetch_ticket(ticket_id: str) -> dict:
    print(f"Fetching ticket {ticket_id} from {JIRA_BASE_URL} ...")
    fields_param = (
        "summary,description,status,priority,reporter,assignee,"
        "labels,components,comment,attachment,issuetype"
    )
    data = api_get(f"issue/{ticket_id}", params={"fields": fields_param})
    fields = data.get("fields", {})

    # Basic fields
    title = fields.get("summary", "")
    status = (fields.get("status") or {}).get("name", "Unknown")
    priority = (fields.get("priority") or {}).get("name", "Unknown")
    reporter = ((fields.get("reporter") or {}).get("displayName") or
                (fields.get("reporter") or {}).get("emailAddress", "Unknown"))
    assignee = ((fields.get("assignee") or {}).get("displayName") or
                (fields.get("assignee") or {}).get("emailAddress", "Unassigned"))
    labels = fields.get("labels", [])
    components = [c.get("name", "") for c in fields.get("components", [])]
    description = safe_flatten(fields.get("description"))

    # Comments
    comments_raw = (fields.get("comment") or {}).get("comments", [])
    comments = []
    for c in comments_raw:
        author = ((c.get("author") or {}).get("displayName") or
                  (c.get("author") or {}).get("emailAddress", "Unknown"))
        created = c.get("created", "")
        body = safe_flatten(c.get("body"))
        comments.append({"author": author, "created": created, "body": body})

    # Attachments
    attachments_raw = fields.get("attachment", [])
    print(f"  Found {len(attachments_raw)} attachment(s). Downloading ...")
    attachments = download_attachments(ticket_id, attachments_raw)

    ticket_url = f"{JIRA_BASE_URL}/browse/{ticket_id}"

    sections = parse_bug_report_sections(description)

    return {
        "ticket_id": ticket_id,
        "url": ticket_url,
        "title": title,
        "description": description,
        "status": status,
        "priority": priority,
        "reporter": reporter,
        "assignee": assignee,
        "labels": labels,
        "components": components,
        "comments": comments,
        "attachments": attachments,
        # Structured bug-report sections (parsed from description). Empty
        # string when a section is absent so the state shape is stable.
        "reproduction_steps":  sections["reproduction_steps"],
        "current_behavior":    sections["current_behavior"],
        "expected_behavior":   sections["expected_behavior"],
        "actual_result":       sections["actual_result"],
        "expected_result":     sections["expected_result"],
        "acceptance_criteria": sections["acceptance_criteria"],
        # Workflow tracking — reset on every fresh fetch
        "current_step": 1,
        "reproduced": False,
        "root_cause": None,
        "files_to_change": [],
        "fix_attempts": 0,
        "test_results": None,
    }


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python3 fetch_jira.py <TICKET_ID_OR_URL>")
        print("Examples:")
        print("  python3 fetch_jira.py PROJ-456")
        print("  python3 fetch_jira.py https://yourcompany.atlassian.net/browse/PROJ-456")
        sys.exit(1)

    validate_env()
    ticket_id = parse_ticket_id(sys.argv[1])
    state = fetch_ticket(ticket_id)

    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved to {STATE_FILE}")
    print(f"  Ticket : {state['ticket_id']}")
    print(f"  Title  : {state['title']}")
    print(f"  Status : {state['status']}")
    print(f"  Priority: {state['priority']}")
    print(f"  Comments: {len(state['comments'])}")
    print(f"  Attachments: {len(state['attachments'])}")

    print_bug_report_summary(state)

    print("\nStep 1 complete.")
    print("MANDATORY NEXT: Step 2 (bug-reproducer skill) — runtime reproduction")
    print("required before Step 3 (Investigate). Use the sections above as the")
    print("reproduction script. Do NOT skip to investigation.")


if __name__ == "__main__":
    main()
