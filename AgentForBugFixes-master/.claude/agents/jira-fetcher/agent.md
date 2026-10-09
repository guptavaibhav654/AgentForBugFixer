---
name: jira-fetcher
description: Fetches a Jira ticket (including comments and attachments) and writes all data to .bug-fix-state.json for the bug-fixing workflow.
when_to_use: Use this skill as Step 1 of the bug-fixing workflow whenever you are given a Jira ticket ID or URL. Always run this before any other step.
---

# Jira Fetcher Skill

## Purpose
Retrieve complete Jira ticket data — title, description, status, priority, reporter, assignee, labels, components, comments, and attachments — and persist it to `.bug-fix-state.json` so every subsequent skill can read it without re-authenticating.

## Prerequisites
Create a `.env` file at the repo root (copy from `.env.example`) with:
```
JIRA_BASE_URL=https://your-company.atlassian.net
JIRA_EMAIL=you@company.com
JIRA_API_TOKEN=ATATT_your_token_here
```
Get your API token at: https://id.atlassian.com/manage/api-tokens

Install dependencies once:
```bash
pip install -r .claude/agents/requirements.txt
```

## Usage
```bash
python3 .claude/agents/jira-fetcher/scripts/fetch_jira.py <TICKET_ID_OR_URL>
```

Examples:
```bash
python3 .claude/agents/jira-fetcher/scripts/fetch_jira.py PROJ-456
python3 .claude/agents/jira-fetcher/scripts/fetch_jira.py https://your-company.atlassian.net/browse/PROJ-456
```

## Output
Writes `.bug-fix-state.json` at the repo root with these fields:
- `ticket_id` — e.g. `"PROJ-456"`
- `url` — full Atlassian URL
- `title` — issue summary
- `description` — flattened plain text (ADF converted)
- `status` — current workflow status
- `priority` — e.g. `"High"`
- `reporter` / `assignee` — display names
- `labels` / `components` — arrays
- `comments` — array of `{ author, created, body }` objects (ADF flattened)
- `attachments` — array of `{ filename, url, local_path }` objects
- `current_step` — initialized to `1`
- `reproduced` — initialized to `false`
- `root_cause` — initialized to `null`
- `files_to_change` — initialized to `[]`
- `fix_attempts` — initialized to `0`
- `test_results` — initialized to `null`

## ADF Flattening
Jira Cloud returns descriptions and comments in Atlassian Document Format (ADF — nested JSON). This skill walks the ADF tree and extracts all text nodes into a readable plain-text string. Code blocks are preserved with a `CODE:` prefix.

## Attachments
Image and file attachments are downloaded to `.tmp/attachments/<ticket_id>/` so the `bug-reproducer` and `bug-investigator` skills can inspect screenshots or log files. The `.tmp/` directory is git-ignored.

## Notes
- The script is idempotent: running it again on the same ticket overwrites `.bug-fix-state.json` but resets `current_step` to `1`.
- Never commit `.bug-fix-state.json` — it may contain sensitive ticket data.
- If the ticket is not found, the script exits with a non-zero code and a clear error message.
