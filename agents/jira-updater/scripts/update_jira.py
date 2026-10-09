#!/usr/bin/env python3
"""
update_jira.py — Post fix summary to Jira, transition ticket, add label.
Usage: python update_jira.py
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
    print("ERROR: Missing dependencies. Run: pip install requests python-dotenv")
    sys.exit(1)

_cwd = Path.cwd()
for _parent in [_cwd] + list(_cwd.parents):
    _env_file = _parent / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
        break

JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "").rstrip("/")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")

STATE_FILE = Path(".bug-fix-state.json")


def validate_env() -> None:
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
    return {
        "Authorization": f"Bearer {JIRA_API_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def api_get(path: str, params: dict = None) -> dict:
    url = f"{JIRA_BASE_URL}/rest/api/2/{path.lstrip('/')}"
    resp = requests.get(url, headers=auth_headers(), params=params or {}, timeout=30)
    if resp.status_code == 401:
        print("ERROR: Authentication failed. Check JIRA_API_TOKEN.")
        sys.exit(1)
    resp.raise_for_status()
    return resp.json()


def api_post(path: str, body: dict) -> requests.Response:
    url = f"{JIRA_BASE_URL}/rest/api/2/{path.lstrip('/')}"
    return requests.post(url, headers=auth_headers(), json=body, timeout=30)


def api_put(path: str, body: dict) -> requests.Response:
    url = f"{JIRA_BASE_URL}/rest/api/2/{path.lstrip('/')}"
    return requests.put(url, headers=auth_headers(), json=body, timeout=30)


def build_comment(state: dict) -> dict:
    ticket_id = state.get("ticket_id", "Unknown")
    root_cause = state.get("root_cause") or "Not documented."
    fix_description = state.get("fix_description") or "See files changed."
    files_changed = state.get("files_changed") or state.get("files_to_change") or []
    test_results = state.get("test_results") or "Not recorded."
    fix_attempts = state.get("fix_attempts", 1)

    branch = state.get("branch") or "Not set."
    commit_sha = state.get("commit_sha") or "Not set."
    commit_short = commit_sha[:8] if commit_sha and commit_sha != "Not set." else commit_sha

    pr_url = state.get("pr_url")
    pr_number = state.get("pr_number")
    if pr_url and pr_number:
        pr_line = f"[GitHub PR #{pr_number}|{pr_url}]"
    elif pr_url:
        pr_line = f"[GitHub PR|{pr_url}]"
    else:
        pr_line = "Not yet created."

    files_block = (
        "\n".join(f"* {{{{{f}}}}}" for f in files_changed)
        if files_changed else "No files recorded."
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


def add_comment(ticket_id: str, state: dict) -> bool:
    print(f"Posting comment to {ticket_id} ...")
    resp = api_post(f"issue/{ticket_id}/comment", build_comment(state))
    if resp.status_code in (200, 201):
        print(f"  Comment posted (id={resp.json().get('id', '?')}).")
        return True
    print(f"  ERROR: Failed to post comment. Status {resp.status_code}: {resp.text[:300]}")
    return False


def get_transitions(ticket_id: str) -> list:
    return api_get(f"issue/{ticket_id}/transitions").get("transitions", [])


def transition_to(ticket_id: str, target_name: str) -> bool:
    transitions = get_transitions(ticket_id)
    match = next(
        (t for t in transitions if target_name.lower() in t.get("name", "").lower()),
        None,
    )
    if not match:
        available = [t.get("name", "") for t in transitions]
        print(f"  WARNING: Transition '{target_name}' not available. Available: {available}")
        return False
    print(f"  Transitioning to '{match['name']}' ...")
    resp = api_post(f"issue/{ticket_id}/transitions", {"transition": {"id": match["id"]}})
    if resp.status_code == 204:
        print(f"  Transitioned to '{match['name']}' successfully.")
        return True
    print(f"  WARNING: Transition failed. Status {resp.status_code}: {resp.text[:200]}")
    return False


def add_label(ticket_id: str, label: str) -> bool:
    print(f"  Adding label '{label}' to {ticket_id} ...")
    data = api_get(f"issue/{ticket_id}", params={"fields": "labels"})
    current_labels = list(data.get("fields", {}).get("labels", []))
    if label in current_labels:
        print(f"  Label '{label}' already present.")
        return True
    current_labels.append(label)
    resp = api_put(f"issue/{ticket_id}", {"fields": {"labels": current_labels}})
    if resp.status_code == 204:
        print(f"  Label '{label}' added.")
        return True
    print(f"  WARNING: Failed to add label. Status {resp.status_code}: {resp.text[:200]}")
    return False


def add_remote_link(ticket_id: str, pr_url: str, pr_number: int) -> bool:
    print(f"  Adding remote link (PR #{pr_number}) to {ticket_id} ...")
    payload = {
        "object": {
            "url": pr_url,
            "title": f"GitHub PR #{pr_number}",
            "icon": {"url16x16": "https://github.com/favicon.ico"},
        }
    }
    url = f"{JIRA_BASE_URL}/rest/api/2/issue/{ticket_id}/remotelink"
    resp = requests.post(url, headers=auth_headers(), json=payload, timeout=30)
    if resp.status_code in (200, 201):
        print("  Remote link added.")
        return True
    print(f"  WARNING: Failed to add remote link. Status {resp.status_code}: {resp.text[:200]}")
    return False


def main() -> None:
    validate_env()
    state = load_state()
    ticket_id = state.get("ticket_id")

    if not ticket_id:
        print("ERROR: 'ticket_id' not found in .bug-fix-state.json.")
        sys.exit(1)

    print(f"\nUpdating Jira ticket: {ticket_id}")
    print(f"  URL: {JIRA_BASE_URL}/browse/{ticket_id}\n")

    comment_ok = add_comment(ticket_id, state)
    if not comment_ok:
        print("ERROR: Comment posting failed. Aborting Jira update.")
        sys.exit(1)

    transition_used = None
    if transition_to(ticket_id, "In Review"):
        transition_used = "In Review"
    elif transition_to(ticket_id, "Start Progress"):
        transition_used = "Start Progress"

    add_label(ticket_id, "bug-fixer-agent")

    pr_url = state.get("pr_url")
    pr_number = state.get("pr_number")
    if pr_url and pr_number:
        add_remote_link(ticket_id, pr_url, pr_number)

    state["jira_updated"] = True
    state["jira_transition"] = transition_used
    state["current_step"] = 12
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    print(f"\nJira update complete for {ticket_id}.")
    print("State updated: current_step=12, jira_updated=true")


if __name__ == "__main__":
    main()
