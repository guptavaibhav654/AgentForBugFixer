---
name: pr-creator
description: Creates a GitHub Pull Request for the bugfix branch using the gh CLI (preferred) or a Python fallback script, then stores the PR URL and number in state.
when_to_use: Use this skill as Step 11 of the bug-fixing workflow, after the branch has been pushed to origin (Step 10) and before updating Jira (Step 12).
---

# PR Creator Skill

> **For GitHub remotes only.** If the repo's `origin` points at a GitLab instance (gitlab.com or self-hosted, e.g. `githyd.epam.com`), use the `gitlab-mr` skill instead. Detect via `git remote -v`.

## Purpose
Open a structured GitHub Pull Request for the bugfix branch. The PR title and body are derived from the Jira ticket and state file so the PR is immediately reviewable with full context.

## PR Title Format
```
fix({scope}): {title} ({TICKET-ID})
```

**Examples:**
```
fix(backend): prevent NPE when cultural score list is null (EPMICMPSTP-482)
fix(frontend): restore submit button visibility on mobile (UI-99)
fix(core): align DTO validation between BE and FE (PROJ-456)
```

Scope follows the same rules as git-committer:
- `backend` — changes only under `step-epamin-develop/`
- `frontend` — changes only under `step-ui-develop/step-ui-develop/`
- `core` — both, or root-level files

## PR Body Template
```markdown
## Summary
<!-- 1-2 sentences describing what the PR fixes -->
Fixes {TICKET-ID}: {ticket_title}

## Jira Ticket
{jira_url}

## Root Cause
{root_cause}

## Files Changed
{files_changed_list}

## Test Results
- Status: {test_results}
- Fix attempts: {fix_attempts}

## Checklist
- [ ] Passes all existing tests
- [ ] New/updated test added for the bug scenario
- [ ] No secrets or build artifacts committed
- [ ] Reviewed by a human before merging

---
*This PR was created by the Bug Fixer Agent. Do not merge without human review.*
```

## Method 1: gh CLI (Preferred)

### Prerequisites
```bash
# Verify gh is installed and authenticated
gh auth status
```

### Command
```bash
gh pr create \
  --base main \
  --head bugfix/{TICKET-ID}-{slug} \
  --title "fix({scope}): {title} ({TICKET-ID})" \
  --body "$(cat <<'EOF'
## Summary
Fixes {TICKET-ID}: {ticket_title}

## Jira Ticket
{jira_url}

## Root Cause
{root_cause}

## Files Changed
{files_changed_list}

## Test Results
- Status: {test_results}
- Fix attempts: {fix_attempts}

## Checklist
- [ ] Passes all existing tests
- [ ] New/updated test added for the bug scenario
- [ ] No secrets or build artifacts committed
- [ ] Reviewed by a human before merging

---
*This PR was created by the Bug Fixer Agent. Do not merge without human review.*
EOF
)"
```

The `gh` CLI outputs the PR URL. Capture it:
```bash
PR_URL=$(gh pr create ... )
PR_NUMBER=$(gh pr view --json number --jq '.number')
```

## Method 2: Python Script (Fallback)

If `gh` CLI is not available or not authenticated:
```bash
python3 .claude/skills/pr-creator/scripts/create_pr.py
```

The script reads all context from `.bug-fix-state.json` and environment variables. See `scripts/create_pr.py` for implementation details.

### Required Environment Variables
```
GITHUB_TOKEN=ghp_your_token_here
GITHUB_USER=your-username
```
These must be in `.env` (walked up from cwd).

## State Update
After a successful PR creation, update `.bug-fix-state.json`:
```json
{
  "pr_url": "https://github.com/owner/repo/pull/123",
  "pr_number": 123,
  "current_step": 11
}
```

## Error Conditions

| Condition | Response |
|-----------|----------|
| `gh` not installed | Fall back to Python script automatically |
| `gh` not authenticated | Run `gh auth login`, or fall back to Python script |
| `GITHUB_TOKEN` missing | Check `.env`, add token and retry |
| Branch not pushed | Run `git push -u origin {branch}` first (Step 10) |
| PR already exists | Capture existing PR URL, update state, continue |
| API rate limit | Wait and retry, or ask user |

## Notes
- Target branch is always `main` (the default branch of this repo).
- PRs are created as **draft** only if explicitly requested by the user.
- Never set PR to auto-merge.
- The PR URL stored in state will be included in the Jira comment and as a remote link (Step 12).
