---
name: git-brancher
description: Creates a properly named bugfix branch for the current Jira ticket, with safety checks to ensure the working tree is clean and the branch does not already exist.
when_to_use: Use this skill as Step 5 of the bug-fixing workflow, after the fix plan is approved (Step 4) and before applying any code changes (Step 6).
---

# Git Brancher Skill

## Purpose
Create a dedicated bugfix branch for every Jira ticket fix. This ensures changes are isolated from `main`, traceable to a ticket, and reviewable via a PR before merging.

> **Default branch for this repo**: `main`

## Branch Naming Convention
```
bugfix/{TICKET-ID}-{slug}
```

### Slug Rules
- Take the Jira ticket title (or a short human description of the bug)
- Lowercase everything
- Replace spaces and underscores with hyphens `-`
- Remove all characters that are not alphanumeric or hyphens
- Truncate to 40 characters maximum
- Remove leading/trailing hyphens

**Examples:**
| Ticket | Title | Branch |
|--------|-------|--------|
| PROJ-456 | NullPointerException on login | `bugfix/PROJ-456-nullpointerexception-on-login` |
| EPMICMPSTP-482 | Cultural score not saved for Q4 | `bugfix/EPMICMPSTP-482-cultural-score-not-saved-for-q4` |
| UI-99 | Button disappears on mobile view | `bugfix/UI-99-button-disappears-on-mobile-view` |

## Safety Checks (ALL must pass before creating branch)

### 1. Clean Working Tree
```bash
git status --porcelain
```
- Output must be empty.
- If not empty: STOP. Do not create the branch. Tell the user to commit, stash, or discard changes first.

### 2. On Default Branch
```bash
git rev-parse --abbrev-ref HEAD
```
- Must return `main`.
- If on a different branch: STOP. Ask user to confirm — they may be resuming an existing fix. If resuming, skip branch creation and use the existing branch.

### 3. Pull Latest
```bash
git pull origin main
```
- Must succeed. If it fails (merge conflict, network error): STOP and report the error.

### 4. Branch Must Not Exist
```bash
git branch --list bugfix/{TICKET-ID}-{slug}
```
- Output must be empty.
- If branch already exists: ASK user whether to:
  a. Checkout the existing branch (resume previous work), or
  b. Create a new branch with a suffix `-v2`, `-v3`, etc.

## Usage (Commands to Run)

```bash
# Check for clean tree
git status --porcelain

# Ensure on main
git rev-parse --abbrev-ref HEAD

# Pull latest changes
git pull origin main

# Create and checkout the branch
git checkout -b bugfix/{TICKET-ID}-{slug}

# Verify branch was created
git rev-parse --abbrev-ref HEAD
```

## State Update
After successfully creating the branch, update `.bug-fix-state.json`:
```json
{
  "branch": "bugfix/PROJ-456-short-description",
  "current_step": 5
}
```

## Error Conditions

| Condition | Response |
|-----------|----------|
| Dirty working tree | STOP. List untracked/modified files. Ask user to resolve. |
| Not on `main` | STOP. Report current branch. Ask user intent. |
| `git pull` fails | STOP. Report the git error message verbatim. |
| Branch already exists | ASK: resume or create `-v2`? |
| `git checkout -b` fails | STOP. Report error. Check for name conflicts. |

## Notes
- Never use `git checkout -B` (force) — it would reset an existing branch.
- Never commit anything in this skill — this skill only creates the branch.
- The branch will be pushed to origin in Step 10 (after validation).
