# Bug-Fix Agent Workflow

Automated 13-step pipeline for resolving Jira tickets — from ticket fetch to merged PR.

---

## Overview

```
USER: "Fix PROJ-456"
        │
        ▼
┌─────────────────────────┐
│   🟢 PHASE A: UNDERSTAND │
├─────────────────────────┤
│   🟡 PHASE B: FIX        │
├─────────────────────────┤
│   🚀 PHASE C: SHIP       │
└─────────────────────────┘
        │
        ▼
   ✅ PR / MR ready for review
```

---

## 🟢 Phase A — Understand

### Step 1 · Fetch Jira Ticket
> **Skill:** `jira-fetcher`

- Pull ticket description, comments, and attachments
- Save `reproduction_steps`, `expected_behavior`, `actual_behavior`
- Write state: `current_step = 1`

---

### Step 2 · Reproduce Bug &nbsp;🔴 BLOCKING
> **Skill:** `bug-reproducer`

- **Must** runtime-reproduce — no shortcuts or assumptions
- Capture HTTP status code, logs, DB row, screenshot as evidence
- Maximum **3 attempts** — stop and escalate if all fail
- Write `reproduction_evidence` to state

---

### Step 3 · Investigate
> **Skill:** `bug-investigator`
> **Precondition:** `reproduced == true`

- Code search + `git blame` to trace origin
- Write `root_cause` to state

---

### Step 4 · Plan Fix
> *(agent reasoning — no skill)*

- List minimal `files_to_change`
- Self-check for risks and side effects

---

## 🟡 Phase B — Fix

### Step 5 · Create Branch
> **Skill:** `git-brancher`

- Verify clean working tree
- Pull latest `main`
- Branch naming: `bugfix/PROJ-456-{slug}`

---

### Step 6 · Apply Fix
> **Skill:** `code-fixer`

- Edit **only** the files listed in `files_to_change`
- Match existing code style and conventions

---

### Step 7 · Add Tests

- Backend → JUnit &nbsp;|&nbsp; Frontend → Jest
- Test **must fail** without the fix applied

---

### Step 8 · Validate
> **Skill:** `fix-validator`

- Run `mvn test` (backend) or `npm test` (frontend)
- **Pass** → continue to Phase C
- **Fail** → loop back to Step 6 (max 3 retries)
- 3 consecutive failures → stop and ask user

```
        ┌─────────────────────────────┐
        │  fail → retry Step 6        │
Step 8 ─┤                             │
        │  pass → continue to Phase C │
        └─────────────────────────────┘
```

---

## 🚀 Phase C — Ship

### Step 9 · Commit
> **Skill:** `git-committer`

- Stage only the intended files
- Scan for secrets before committing
- Use [Conventional Commits](https://www.conventionalcommits.org/) format

---

### Step 10 · Push Branch

```bash
git push -u origin <branch>
```

- Verify push succeeded before proceeding

---

### Step 11 · Open PR / MR

Detect remote automatically:

| Remote URL pattern | Tool used |
|---|---|
| `github.*` | `pr-creator` via `gh` CLI |
| `gitlab.*` | `gitlab-mr` via Python + API |

---

### Step 12 · Update Jira
> **Skill:** `jira-updater`

- Post comment with PR / MR link
- Add remote link to ticket
- Transition status: **In Review → Start Progress**
- Apply label: `bug-fixer-agent`

---

### Step 13 · Summary

Print final report:

| Field | Value |
|---|---|
| Branch | `bugfix/PROJ-456-{slug}` |
| Commit SHA | `abc1234` |
| PR URL | `https://github.com/.../pull/123` |
| Jira URL | `https://yourorg.atlassian.net/browse/PROJ-456` |
| Files changed | list of modified files |
| Tests added | test file names |
| Next steps | reviewer actions |

---

## ✅ Done

> User reviews the PR / MR and merges.

---

## Full Flow at a Glance

```
"Fix PROJ-456"
      │
      ▼
╔══════════════════════════════════════╗
║         🟢 PHASE A: UNDERSTAND        ║
║                                      ║
║  Step 1 ── Fetch Jira ticket         ║
║      │                               ║
║  Step 2 ── Reproduce bug  🔴BLOCKING  ║
║      │     (3 attempts max)          ║
║  Step 3 ── Investigate root cause    ║
║      │                               ║
║  Step 4 ── Plan fix                  ║
╚══════════════════════════════════════╝
      │
      ▼
╔══════════════════════════════════════╗
║           🟡 PHASE B: FIX             ║
║                                      ║
║  Step 5 ── Create branch             ║
║      │                               ║
║  Step 6 ── Apply fix         ◄───┐   ║
║      │                           │   ║
║  Step 7 ── Add tests             │   ║
║      │                           │   ║
║  Step 8 ── Validate       ───────┘   ║
║            (fail → retry, max 3x)    ║
╚══════════════════════════════════════╝
      │
      ▼
╔══════════════════════════════════════╗
║           🚀 PHASE C: SHIP            ║
║                                      ║
║  Step  9 ── Commit                   ║
║  Step 10 ── Push branch              ║
║  Step 11 ── Open PR / MR             ║
║  Step 12 ── Update Jira              ║
║  Step 13 ── Print summary            ║
╚══════════════════════════════════════╝
      │
      ▼
   ✅ DONE — User reviews & merges
```