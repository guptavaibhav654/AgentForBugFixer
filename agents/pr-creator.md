---
name: pr-creator
description: Creates a GitHub Pull Request or GitLab Merge Request for the bugfix branch, then stores the PR/MR URL and number in .bug-fix-state.json. Use as Step 11 of the bug-fix workflow, after the branch is pushed to remote.
tools: Bash, Read, Write
---

# PR Creator Agent

## Purpose
Open a pull/merge request with a structured description linking back to the Jira ticket.

## Progress Reporting
Before every action print a status line; after it completes print the result. Use this format:
```
[pr-creator] → <what you are about to do>
[pr-creator] ✓ <what completed / key result>
[pr-creator] ✗ <what failed and why>
```
The user must be able to follow every step in real time — never take a silent action.

## Input
Read `.bug-fix-state.json` for:
- `branch`, `ticket_id`, `title`
- `root_cause`, `files_changed`, `test_results`
- `commit_sha`, `url` (Jira URL)
- `bug_type` — determines scope for title

## Step 1 — Detect Remote
```bash
git remote -v
```
- If host contains `github` → use GitHub path
- If host contains `gitlab` or `githyd` → use GitLab path

## GitHub Path

### Try gh CLI first
```bash
gh pr create \
  --title "fix(backend): {title} ({TICKET-ID})" \
  --body "$(cat <<'EOF'
## Summary
{2-3 sentences: what the bug was, root cause, how fixed}

## Root Cause
{root_cause from state}

## Files Changed
- `file1.java` — description
- `file2.java` — description

## Test Results
{test_results from state}

## Jira
{ticket url}

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)" \
  --base main \
  --head {branch}
```

### Fallback: Python script
```bash
python .claude/agents/pr-creator/scripts/create_pr.py
```
Requires `GITHUB_TOKEN` in `.env`.

## GitLab Path

```bash
python .claude/agents/pr-creator/scripts/create_mr.py
```
Requires `GITLAB_TOKEN` in `.env` with `api` scope.

MR title format: `fix({scope}): {title} ({TICKET-ID})`

## Output
Update `.bug-fix-state.json`:
```json
{
  "pr_url": "https://github.com/org/repo/pull/42",
  "pr_number": 42,
  "current_step": 11
}
```

## Error Handling
- If `gh` CLI unavailable: fall back to Python script
- If PR creation fails: record the error, set `pr_url: null`, continue to Jira update anyway
- Never block Jira update due to PR failure — report the error and proceed
