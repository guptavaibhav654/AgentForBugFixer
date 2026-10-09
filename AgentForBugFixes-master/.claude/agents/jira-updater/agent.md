---
name: jira-updater
description: Posts a structured comment to the Jira ticket summarising the fix, transitions the ticket to "In Review", and adds the bug-fixer-agent label.
when_to_use: Use this skill as Step 8 of the bug-fixing workflow, after fix-validator confirms all tests pass. Never use before validation is complete.
---

# Jira Updater Skill

## Purpose
Close the loop with the Jira ticket: post a detailed, structured comment describing what was found and fixed, move the ticket to "In Review" status, and tag it so the team knows the fix came from the automated agent.

## Prerequisites
The same `.env` credentials used by `jira-fetcher` are required:
```
JIRA_BASE_URL=https://your-company.atlassian.net
JIRA_EMAIL=you@company.com
JIRA_API_TOKEN=ATATT_your_token_here
```

## Usage
```bash
python3 .claude/agents/jira-updater/scripts/update_jira.py
```

The script reads everything it needs from `.bug-fix-state.json` — no arguments required.

## What the Script Does
1. Reads `.bug-fix-state.json` for `ticket_id`, `root_cause`, `files_changed`, `fix_description`, `test_results`, `fix_attempts`.
2. Builds a structured ADF comment (Atlassian Document Format) with the template below.
3. Posts the comment to the Jira REST API.
4. Fetches available transitions for the ticket.
5. Transitions the ticket to **"In Review"** (if available).
6. Adds the label `bug-fixer-agent` to the ticket.

## Comment Template
The posted comment will look like:

```
[Bug Fixer Agent] Fix Applied

Root Cause
<value of root_cause from state file>

Fix Description
<value of fix_description from state file>

Files Changed
• path/to/FileOne.java
• path/to/FileTwo.tsx

Test Results
Status: passed
Attempts: 1

Next Steps
Please review the changes locally and commit after approval.
The ticket has been moved to "In Review".

---
Fixed by Bug Fixer Agent (automated) — do not merge without human review.
```

## Transition Rules
- ALWAYS transition to **"In Review"** — this signals human review is needed.
- NEVER transition to **"Done"**, **"Closed"**, or **"Resolved"** — only a human can do that.
- If "In Review" is not available as a transition, log a warning and skip the transition (do not fail).
- The `get_transitions` function fetches the live list of valid transitions so it adapts to any Jira workflow configuration.

## Label
The script adds `bug-fixer-agent` to the ticket's labels. This allows the team to filter and audit all issues touched by the automated agent.

## Error Handling
- If the comment POST fails, the script prints the error and exits with code 1.
- If the transition fails (e.g., workflow does not allow it from current status), it logs a warning but continues to attempt the label update.
- If label update fails, it logs a warning and exits cleanly (the comment was already posted).

## Notes
- The script uses the Jira REST API v2 (`/rest/api/2/`) against the instance configured in `JIRA_BASE_URL`.
- Comments are posted as plain Jira wiki markup `{"body": "<string>"}` — NOT ADF. The v2 API accepts wiki markup directly.
- Authentication uses `Authorization: Bearer {PAT}` — NOT `HTTPBasicAuth` or `JIRA_EMAIL`.
- `JIRA_EMAIL` is not required for Jira DC.
- Never commit `.bug-fix-state.json` — it contains ticket metadata.

---

## Phase 2 Additions (Semi-Auto Mode)

### PR Link in Comment
The comment body now includes a "Pull Request" section near the top:
```
h3. Pull Request
*PR:* [GitHub PR #123|https://github.com/owner/repo/pull/123]
*Branch:* bugfix/PROJ-456-short-description
*Commit:* abc12345
```
If `pr_url` is not yet set in state when the script runs, the PR line shows "Not yet created."

### Remote Link
After posting the comment, the script calls `add_remote_link(ticket_id, pr_url, pr_number)` which POSTs to:
```
POST /rest/api/2/issue/{ticket_id}/remotelink
{
  "object": {
    "url": "https://github.com/owner/repo/pull/123",
    "title": "GitHub PR #123",
    "icon": {"url16x16": "https://github.com/favicon.ico"}
  }
}
```
This adds the PR as a linked web resource visible on the Jira issue sidebar. The remote link is only added when both `state["pr_url"]` and `state["pr_number"]` are present.

### Transition Fallback
If the configured Jira workflow does not offer an "In Review" transition, the script uses a two-step fallback:
1. First tries `transition_to(ticket_id, "In Review")` — succeeds if the workflow has it.
2. If that returns `False` (transition not available), falls back to `transition_to(ticket_id, "Start Progress")`.
3. If neither is available, logs all available transitions and continues (does not fail the overall update).

### State Update on Completion
After a successful Jira update, the script writes back to `.bug-fix-state.json`:
```json
{
  "jira_updated": true,
  "current_step": 13
}
```
This allows the workflow to detect that Jira has already been updated if the process is interrupted after this step.
