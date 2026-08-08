#!/usr/bin/env python3
"""
create_mr.py — Open a GitLab Merge Request for the current bug-fix branch.
Usage: python create_mr.py
Reads .bug-fix-state.json from the current working directory.
Requires GITLAB_TOKEN (scope: api) in .env.
"""

import json
import os
import re
import subprocess
import sys
import urllib.parse
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

GITLAB_TOKEN = os.getenv("GITLAB_TOKEN", "")
STATE_FILE = Path(".bug-fix-state.json")


def fail(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}")
    sys.exit(code)


def auth_headers() -> dict:
    return {
        "PRIVATE-TOKEN": GITLAB_TOKEN,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def parse_remote(remote_url: str) -> tuple[str, str]:
    url = remote_url.strip()
    m = re.match(r"^[^@]+@([^:/]+):(.+)$", url)
    if m:
        host, path = m.group(1), m.group(2)
        return f"https://{host}", path.removesuffix(".git")
    if url.startswith("ssh://"):
        rest = url[len("ssh://"):]
        m = re.match(r"^(?:[^@]+@)?([^:/]+)(?::\d+)?/(.+)$", rest)
        if m:
            host, path = m.group(1), m.group(2)
            return f"https://{host}", path.removesuffix(".git")
    if url.startswith("http://") or url.startswith("https://"):
        scheme_end = url.index("://") + 3
        rest = url[scheme_end:]
        host, _, path = rest.partition("/")
        scheme = url[:scheme_end - 3]
        return f"{scheme}://{host}", path.removesuffix(".git")
    fail(f"Could not parse git remote URL: {remote_url}")


def get_remote_url() -> str:
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        fail("No git remote 'origin' configured.")


def load_state() -> dict:
    if not STATE_FILE.exists():
        fail(f"{STATE_FILE} not found. Run jira-fetcher first.")
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    branch = state.get("branch") or state.get("branch_name")
    if not branch:
        fail("State missing 'branch'. Run git-brancher (Step 5) first.")
    if not state.get("ticket_id"):
        fail("State missing 'ticket_id'. Run jira-fetcher (Step 1) first.")
    return state


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def detect_scope(files_changed: list[str]) -> str:
    if not files_changed:
        return "core"
    backend = all(f.startswith("step-epamin-develop/") for f in files_changed)
    frontend = all(f.startswith("step-ui-develop/") for f in files_changed)
    if backend:
        return "backend"
    if frontend:
        return "frontend"
    return "core"


def strip_jira_prefix(title: str) -> str:
    return re.sub(r"^\[[^\]]+\]\s*", "", title).strip()


def build_title(state: dict) -> str:
    scope = detect_scope(state.get("files_changed", []))
    cleaned = strip_jira_prefix(state.get("title", "fix applied"))
    return f"fix({scope}): {cleaned} ({state['ticket_id']})"


def build_description(state: dict) -> str:
    files_changed = state.get("files_changed", [])
    commit_sha = state.get("commit_sha", "")
    commit_short = commit_sha[:8] if commit_sha else "(not recorded)"

    files_block = (
        "\n".join(f"- `{f}`" for f in files_changed)
        if files_changed else "_No files recorded._"
    )

    return f"""## Bug Fix: [{state['ticket_id']}]({state.get('url', '')})

**{state.get('title', '')}**

## Root Cause
{state.get('root_cause') or '_Not documented._'}

## Fix
{state.get('fix_description') or '_See files changed._'}

## Files Changed
{files_block}

## Tests
{state.get('test_results') or '_Not recorded._'}

## Reviewer Checklist
- [ ] Root cause makes sense
- [ ] Fix is minimal
- [ ] Tests cover the bug scenario
- [ ] No unrelated changes
- [ ] No secrets in diff

## Links
- Jira: [{state['ticket_id']}]({state.get('url', '')})
- Branch: `{state.get('branch') or state.get('branch_name', '')}`
- Commit: `{commit_short}`

---
*This MR was created automatically by Bug Fixer Agent. Code is AI-assisted — please review carefully.*
"""


def fetch_project(host: str, encoded_path: str) -> dict:
    url = f"{host}/api/v4/projects/{encoded_path}"
    resp = requests.get(url, headers=auth_headers(), timeout=30)
    if resp.status_code == 401:
        fail("401 Unauthorized. GITLAB_TOKEN missing/expired/wrong format.")
    if resp.status_code == 403:
        fail("403 Forbidden. Token lacks `api` scope or project access.")
    if resp.status_code == 404:
        fail(f"404 Not Found. Check project path and token permissions: {url}")
    resp.raise_for_status()
    return resp.json()


def find_existing_mr(host: str, encoded_path: str, source_branch: str) -> dict | None:
    url = f"{host}/api/v4/projects/{encoded_path}/merge_requests"
    resp = requests.get(
        url, headers=auth_headers(),
        params={"state": "opened", "source_branch": source_branch},
        timeout=30,
    )
    resp.raise_for_status()
    matches = resp.json()
    return matches[0] if matches else None


def create_mr_api(host: str, encoded_path: str, payload: dict) -> dict:
    url = f"{host}/api/v4/projects/{encoded_path}/merge_requests"
    resp = requests.post(url, headers=auth_headers(), json=payload, timeout=30)
    if resp.status_code in (200, 201):
        return resp.json()
    if resp.status_code == 409 or "already exists" in resp.text.lower():
        existing = find_existing_mr(host, encoded_path, payload["source_branch"])
        if existing:
            return existing
    fail(f"MR creation failed: {resp.status_code} {resp.text[:600]}")


def main() -> None:
    if not GITLAB_TOKEN:
        fail("GITLAB_TOKEN missing in .env. Add a PAT with `api` scope.")

    state = load_state()
    branch = state.get("branch") or state.get("branch_name")

    remote = get_remote_url()
    host, project_path = parse_remote(remote)
    encoded = urllib.parse.quote(project_path, safe="")

    print(f"GitLab host:    {host}")
    print(f"Project path:   {project_path}")
    print(f"Source branch:  {branch}")

    project = fetch_project(host, encoded)
    target_branch = project["default_branch"]
    print(f"Target branch:  {target_branch} (default)")

    existing = find_existing_mr(host, encoded, branch)
    if existing:
        print(f"\nExisting open MR found: {existing['web_url']}")
        state["pr_url"] = existing["web_url"]
        state["pr_number"] = existing["iid"]
        state["current_step"] = 11
        save_state(state)
        print("State updated with existing MR.")
        return

    payload = {
        "source_branch": branch,
        "target_branch": target_branch,
        "title": build_title(state),
        "description": build_description(state),
        "remove_source_branch": False,
        "labels": "bug,bug-fixer-agent",
    }

    mr = create_mr_api(host, encoded, payload)
    print(f"\nMR created: {mr['web_url']} (IID: {mr['iid']})")

    state["pr_url"] = mr["web_url"]
    state["pr_number"] = mr["iid"]
    state["current_step"] = 11
    save_state(state)
    print("State updated. Step 11 complete.")


if __name__ == "__main__":
    main()
