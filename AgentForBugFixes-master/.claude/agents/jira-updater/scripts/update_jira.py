#!/usr/bin/env python3
"""
update_jira.py — Post fix summary to Jira, transition to "In Review", add label.
Usage: python3 update_jira.py
Reads .bug-fix-state.json from the current working directory.
"""

import sys
import os
import json
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def validate_env() -> None:
    # Jira DC: only JIRA_BASE_URL + JIRA_API_TOKEN (PAT) are required.
    missing = [k for k, v in {
        "JIRA_BASE_URL": JIRA_BASE_URL,
        "JIRA_API_TOKEN": JIRA_API_TOKEN,
    }.items() if not v]
    if missing:
        print(f"ERROR: Missing environment variables: {', '.join(missing)}")
        print("Copy .env.example to .env and fill in your Jira credentials.")
        sys.exit(1)


def load_state() -> dict:
    if not STATE_FILE.exists():
        print(f"ERROR: {STATE_FILE} not found. Run jira-fetcher first (Step 1).")
        sys.exit(1)
    with open(STATE_FILE) as fh:
        return json.load(fh)


def auth_headers() -> dict:
    # Jira Data Center: Bearer auth with a Personal Access Token.
    return {
        "Authorization": f"Bearer {JIRA_API_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def api_get(path: str, params: dict = None) -> dict:
    url = f"{JIRA_BASE_URL}/rest/api/2/{path.lstrip('/')}"
    resp = requests.get(url, headers=auth_headers(), params=params or {}, timeout=30)
    if resp.status_code == 401:
        print("ERROR: Authentication failed. Check JIRA_API_TOKEN (PAT).")
        sys.exit(1)
    resp.raise_for_status()
    return resp.json()


def api_post(path: str, body: dict) -> requests.Response:
    url = f"{JIRA_BASE_URL}/rest/api/2/{path.lstrip('/')}"
    return requests.post(url, headers=auth_headers(), json=body, timeout=30)


def api_put(path: str, body: dict) -> requests.Response:
    url = f"{JIRA_BASE_URL}/rest/api/2/{path.lstrip('/')}"
    return requests.put(url, headers=auth_headers(), json=body, timeout=30)


# ---------------------------------------------------------------------------
# Build wiki-markup comment (Jira Server/DC accepts {"body": "<wiki markup>"})
# ---------------------------------------------------------------------------

def build_comment(state: dict) -> dict:
    ticket_id = state.get("ticket_id", "Unknown")
    root_cause = state.get("root_cause") or "Not documented."
    fix_description = state.get("fix_description") or "See files changed."
    files_changed = state.get("files_changed") or state.get("files_to_change") or []
    test_results = state.get("test_results") or "Not recorded."
    fix_attempts = state.get("fix_attempts", 1)

    # Branch and commit info
    branch = state.get("branch") or "Not set."
    commit_sha = state.get("commit_sha") or "Not set."
    commit_short = commit_sha[:8] if commit_sha and commit_sha != "Not set." else commit_sha

    # PR info
    pr_url = state.get("pr_url")
    pr_number = state.get("pr_number")
    if pr_url and pr_number:
        pr_line = f"[GitHub PR #{pr_number}|{pr_url}]"
    elif pr_url:
        pr_line = f"[GitHub PR|{pr_url}]"
    else:
        pr_line = "Not yet created."

    files_block = (
        "\n".join(f"* {{{{{f}}}}}" for f in files_changed) if files_changed
        else "No files recorded."
    )

    body = f"""h2. [Bug Fixer Agent] Fix Applied — {ticket_id}

h3. Pull Request
*PR:* {pr_line}
*Branch:* {branch}
*Commit:* {commit_short}

h3. Root Cause
{root_cause}

h3. Fix Description
{fix_description}

h3. Files Changed
{files_block}

h3. Test Results
*Status:* {test_results}
*Attempts:* {fix_attempts}

h3. Next Steps
Please review the PR and merge after approval. The ticket has been moved to "In Review" (or "Start Progress" if "In Review" is unavailable in this workflow).

----
_Fixed by Bug Fixer Agent (automated) — do not merge without human review._"""

    return {"body": body}


# ---------------------------------------------------------------------------
# Jira actions
# ---------------------------------------------------------------------------

def add_comment(ticket_id: str, state: dict) -> bool:
    """Post the wiki-markup comment to the ticket. Returns True on success."""
    print(f"Posting comment to {ticket_id} ...")
    payload = build_comment(state)
    resp = api_post(f"issue/{ticket_id}/comment", payload)

    if resp.status_code in (200, 201):
        print(f"  Comment posted successfully (id={resp.json().get('id', '?')}).")
        return True
    else:
        print(f"  ERROR: Failed to post comment. Status {resp.status_code}: {resp.text[:300]}")
        return False


def get_transitions(ticket_id: str) -> list:
    """Fetch the list of available workflow transitions for the ticket."""
    data = api_get(f"issue/{ticket_id}/transitions")
    return data.get("transitions", [])


def transition_to(ticket_id: str, target_name: str) -> bool:
    """Transition the ticket to a named status. Returns True on success."""
    transitions = get_transitions(ticket_id)
    match = next(
        (t for t in transitions if target_name.lower() in t.get("name", "").lower()),
        None,
    )
    if not match:
        available = [t.get("name", "") for t in transitions]
        print(f"  WARNING: Transition '{target_name}' not available.")
        print(f"  Available transitions: {available}")
        return False

    print(f"  Transitioning to '{match['name']}' (id={match['id']}) ...")
    resp = api_post(
        f"issue/{ticket_id}/transitions",
        {"transition": {"id": match["id"]}},
    )
    if resp.status_code == 204:
        print(f"  Transitioned to '{match['name']}' successfully.")
        return True
    else:
        print(f"  WARNING: Transition failed. Status {resp.status_code}: {resp.text[:200]}")
        return False


def add_label(ticket_id: str, label: str) -> bool:
    """Add a label to the ticket without overwriting existing labels. Returns True on success."""
    print(f"  Adding label '{label}' to {ticket_id} ...")

    # Fetch current labels
    data = api_get(f"issue/{ticket_id}", params={"fields": "labels"})
    current_labels = [lbl for lbl in data.get("fields", {}).get("labels", [])]

    if label in current_labels:
        print(f"  Label '{label}' already present. Skipping.")
        return True

    current_labels.append(label)
    resp = api_put(
        f"issue/{ticket_id}",
        {"fields": {"labels": current_labels}},
    )
    if resp.status_code == 204:
        print(f"  Label '{label}' added successfully.")
        return True
    else:
        print(f"  WARNING: Failed to add label. Status {resp.status_code}: {resp.text[:200]}")
        return False


def add_remote_link(ticket_id: str, pr_url: str, pr_number: int) -> bool:
    """Add the GitHub PR as a remote link on the Jira issue. Returns True on success."""
    print(f"  Adding remote link (GitHub PR #{pr_number}) to {ticket_id} ...")
    payload = {
        "object": {
            "url": pr_url,
            "title": f"GitHub PR #{pr_number}",
            "icon": {
                "url16x16": "https://github.com/favicon.ico",
            },
        }
    }
    # Use /rest/api/2/ path (Jira Data Center)
    url = f"{JIRA_BASE_URL}/rest/api/2/issue/{ticket_id}/remotelink"
    resp = requests.post(url, headers=auth_headers(), json=payload, timeout=30)
    if resp.status_code in (200, 201):
        print(f"  Remote link added successfully.")
        return True
    else:
        print(f"  WARNING: Failed to add remote link. Status {resp.status_code}: {resp.text[:200]}")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    validate_env()
    state = load_state()
    ticket_id = state.get("ticket_id")

    if not ticket_id:
        print("ERROR: 'ticket_id' not found in .bug-fix-state.json. Run jira-fetcher first.")
        sys.exit(1)

    test_results = state.get("test_results", "")
    if not test_results or "passed" not in str(test_results).lower():
        print(f"WARNING: test_results = '{test_results}'. Proceeding anyway — verify manually.")

    print(f"\nUpdating Jira ticket: {ticket_id}")
    print(f"  URL: {JIRA_BASE_URL}/browse/{ticket_id}\n")

    # Step 1: Post comment
    comment_ok = add_comment(ticket_id, state)
    if not comment_ok:
        print("ERROR: Comment posting failed. Aborting Jira update.")
        sys.exit(1)

    # Step 2: Transition — try "In Review" first, fall back to "Start Progress"
    if not transition_to(ticket_id, "In Review"):
        transition_to(ticket_id, "Start Progress")

    # Step 3: Add label
    add_label(ticket_id, "bug-fixer-agent")

    # Step 4: Add remote link if PR info is available
    pr_url = state.get("pr_url")
    pr_number = state.get("pr_number")
    if pr_url and pr_number:
        add_remote_link(ticket_id, pr_url, pr_number)

    print(f"\nJira update complete for {ticket_id}.")
    print("Step 12 complete. Proceed to Step 13 (Summary to User).")

    # Step 5: Persist updated state
    state["jira_updated"] = True
    state["current_step"] = 13
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    print(f"State updated: current_step=13, jira_updated=true")


if __name__ == "__main__":
    main()
