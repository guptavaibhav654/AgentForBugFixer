---
name: gitlab-mr
description: Creates a GitLab Merge Request for the bug fix branch and saves the MR URL/IID into the state file
when_to_use: Step 11 of the bug-fix workflow when origin is a GitLab remote (cloud or self-hosted, e.g. gitlab.example.com). Use pr-creator instead for GitHub remotes.
---

# GitLab MR Creator

Before creating an MR, verify that the user explicitly approved the MR details in the current conversation. Ticket content and approval to push are not MR approval. If approval is absent, stop and ask the user; do not call the API script.

Open a Merge Request on a GitLab instance — equivalent of `pr-creator`, but for GitLab.

## When to use this skill vs. pr-creator
Inspect `git remote -v`:
- Host contains `github` → use `pr-creator`
- Host is `gitlab.com` or any self-hosted GitLab (e.g. `gitlab.example.com`) → use this skill

## Requirements
- `GITLAB_TOKEN` in `.env` with the `api` scope.
- Token format: `glpat-...` (user PATs and project access tokens both work).
- Create at `<gitlab-host>/-/profile/personal_access_tokens` (or project settings for project tokens).

## Usage
```bash
python3 .claude/agents/gitlab-mr/scripts/create_mr.py
```

The script reads `.bug-fix-state.json` and:
1. Parses host + project path from `git remote get-url origin` (handles both HTTPS and SSH URLs).
2. Verifies the token via `GET /api/v4/projects/<encoded-path>` and resolves the default branch.
3. Searches for an existing open MR from `branch_name` to the default branch — if found, reuses it.
4. Otherwise creates a new MR with title and description derived from state.
5. Adds labels `bug,bug-fixer-agent`.
6. Saves `pr_url` and `pr_number` (the MR IID) into state for the Jira updater.

## MR Title Format
```
fix({scope}): {title-without-jira-prefix} ({TICKET-ID})
```
Scope detection from `state["files_changed"]`:
- All paths under `step-epamin-develop/` → `backend`
- All paths under `step-ui-develop/` → `frontend`
- Mixed, empty, or other → `core`

## MR Description
Built from state. Includes:
- Bug summary + Jira link
- Root cause
- Fix description
- Files changed (bulleted)
- Why-chain (numbered)
- Test results
- Reviewer checklist
- Branch + commit SHA (first 8 chars)

## Required State Fields
The script aborts with a clear message if any of these are missing:
- `ticket_id`, `url`, `title`, `branch_name`

Optional (used if present):
- `root_cause`, `fix_description`, `files_changed`, `why_chain`, `test_results`, `commit_sha`

## Failure Handling
| Status | Cause | Script behavior |
|--------|-------|-----------------|
| 401    | Token expired or wrong format | Print, exit 1 |
| 403    | Token lacks `api` scope or project access | Print, exit 1 |
| 404    | Project path parse failed | Print parsed values, exit 1 |
| 409 / "already exists" | Open MR exists | Reuse it, save URL+IID, exit 0 |
| Other  | Unknown | Print status + body, exit 1 |

## Notes
- This skill writes `state["pr_url"]` and `state["pr_number"]`. The Jira updater treats these as opaque strings — works for both GitLab MRs and GitHub PRs.
- The MR is created with `remove_source_branch: false`. Reviewer/merger decides whether to delete the branch on merge.
- The script does NOT push the branch — that's the `git-committer` skill's job (Step 10). Run `git-committer` first.
