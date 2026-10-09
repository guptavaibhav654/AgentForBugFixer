#!/usr/bin/env python3
"""
create_pr.py — Create a GitHub Pull Request for the current bugfix branch.
Usage: python3 create_pr.py
Reads .bug-fix-state.json from the current working directory.
Requires GITHUB_TOKEN and GITHUB_USER in .env.
"""

import sys
import os
import json
import subprocess
from pathlib import Path

try:
    import requests
    from dotenv import load_dotenv
except ImportError:
    print("ERROR: Missing dependencies. Run: pip install -r .claude/agents/requirements.txt")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Load environment — walk up from cwd to find .env (matches fetch_jira.py pattern)
# ---------------------------------------------------------------------------
_cwd = Path.cwd()
for _parent in [_cwd] + list(_cwd.parents):
    _env_file = _parent / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
        break

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_USER = os.getenv("GITHUB_USER", "")

STATE_FILE = Path(".bug-fix-state.json")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def validate_env() -> None:
    missing = [k for k, v in {
        "GITHUB_TOKEN": GITHUB_TOKEN,
        "GITHUB_USER": GITHUB_USER,
    }.items() if not v]
    if missing:
        print(f"ERROR: Missing environment variables: {', '.join(missing)}")
        print("Add GITHUB_TOKEN and GITHUB_USER to your .env file.")
        sys.exit(1)


def load_state() -> dict:
    if not STATE_FILE.exists():
        print(f"ERROR: {STATE_FILE} not found. Run jira-fetcher first (Step 1).")
        sys.exit(1)
    with open(STATE_FILE) as fh:
        return json.load(fh)


def github_headers() -> dict:
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_repo_info() -> tuple[str, str]:
    """Return (owner, repo) from git remote origin URL."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, check=True
        )
        url = result.stdout.strip()
        # Handle SSH: git@github.com:owner/repo.git
        if url.startswith("git@github.com:"):
            path = url.replace("git@github.com:", "").rstrip(".git")
        # Handle HTTPS: https://github.com/owner/repo.git
        elif "github.com/" in url:
            path = url.split("github.com/")[-1].rstrip(".git").rstrip("/")
        else:
            print(f"ERROR: Cannot parse GitHub repo from remote URL: {url}")
            sys.exit(1)
        parts = path.split("/")
        if len(parts) < 2:
            print(f"ERROR: Unexpected remote path format: {path}")
            sys.exit(1)
        return parts[0], parts[1]
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: Could not get git remote URL: {exc.stderr}")
        sys.exit(1)


def detect_scope(files: list[str]) -> str:
    """Detect commit scope from list of changed file paths."""
    has_be = any(f.startswith("step-epamin-develop/") for f in files)
    has_fe = any(f.startswith("step-ui-develop/") for f in files)
    if has_be and has_fe:
        return "core"
    if has_be:
        return "backend"
    if has_fe:
        return "frontend"
    return "core"


def build_pr_body(state: dict) -> str:
    ticket_id = state.get("ticket_id", "Unknown")
    ticket_title = state.get("title", "")
    jira_url = state.get("url", "")
    root_cause = state.get("root_cause") or "See commit message."
    files_changed = state.get("files_changed") or state.get("files_to_change") or []
    test_results = state.get("test_results") or "Not recorded."
    fix_attempts = state.get("fix_attempts", 1)

    files_list = (
        "\n".join(f"- `{f}`" for f in files_changed)
        if files_changed
        else "- (see diff)"
    )

    return f"""## Summary
Fixes {ticket_id}: {ticket_title}

## Jira Ticket
{jira_url}

## Root Cause
{root_cause}

## Files Changed
{files_list}

## Test Results
- Status: {test_results}
- Fix attempts: {fix_attempts}

## Checklist
- [ ] Passes all existing tests
- [ ] New/updated test added for the bug scenario
- [ ] No secrets or build artifacts committed
- [ ] Reviewed by a human before merging

---
*This PR was created by the Bug Fixer Agent. Do not merge without human review.*"""


def create_pr(owner: str, repo: str, state: dict) -> dict:
    """Call GitHub API to create a PR. Returns the created PR data dict."""
    ticket_id = state.get("ticket_id", "UNKNOWN")
    branch = state.get("branch")
    if not branch:
        print("ERROR: 'branch' not set in .bug-fix-state.json. Complete Step 5 first.")
        sys.exit(1)

    files_changed = state.get("files_changed") or state.get("files_to_change") or []
    scope = detect_scope(files_changed)
    title_raw = state.get("title", "fix applied")

    pr_title = f"fix({scope}): {title_raw} ({ticket_id})"
    pr_body = build_pr_body(state)

    payload = {
        "title": pr_title,
        "body": pr_body,
        "head": branch,
        "base": "main",
        "draft": False,
    }

    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    print(f"Creating PR in {owner}/{repo}: {pr_title}")
    resp = requests.post(url, headers=github_headers(), json=payload, timeout=30)

    if resp.status_code == 422:
        # PR may already exist — try to find it
        error_msg = resp.json().get("message", "")
        errors = resp.json().get("errors", [])
        if any("already exists" in str(e) for e in errors) or "already exists" in error_msg:
            print("WARNING: PR already exists for this branch. Fetching existing PR...")
            list_url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
            list_resp = requests.get(
                list_url,
                headers=github_headers(),
                params={"head": f"{owner}:{branch}", "state": "open"},
                timeout=30,
            )
            list_resp.raise_for_status()
            prs = list_resp.json()
            if prs:
                print(f"  Found existing PR #{prs[0]['number']}: {prs[0]['html_url']}")
                return prs[0]
        print(f"ERROR: PR creation failed (422): {resp.text[:400]}")
        sys.exit(1)

    if resp.status_code not in (200, 201):
        print(f"ERROR: PR creation failed. Status {resp.status_code}: {resp.text[:400]}")
        sys.exit(1)

    return resp.json()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    validate_env()
    state = load_state()

    owner, repo = get_repo_info()

    pr_data = create_pr(owner, repo, state)

    pr_url = pr_data.get("html_url", "")
    pr_number = pr_data.get("number")

    print(f"\nPR created successfully!")
    print(f"  PR #{pr_number}: {pr_url}")

    # Update state
    state["pr_url"] = pr_url
    state["pr_number"] = pr_number
    state["current_step"] = 11
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    print(f"\nState updated. Step 11 complete. Proceed to jira-updater skill (Step 12).")


if __name__ == "__main__":
    main()
