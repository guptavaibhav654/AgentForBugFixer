# Bug Fixer Agents

This directory contains autonomous AI agents for the Jira bug-fix automation pipeline. Each agent handles one focused responsibility and is orchestrated by the **Bug Fixer Agent** master controller.

## Agent Inventory

| Agent | Purpose |
|-------|---------|
| `jira-fetcher` | Fetches Jira ticket details and saves to state |
| `bug-reproducer` | Reproduces the bug at runtime before any fix |
| `bug-investigator` | Finds root cause via code search and git blame |
| `git-brancher` | Creates a clean `bugfix/` branch from `main` |
| `code-fixer` | Applies the minimal targeted fix |
| `fix-validator` | Runs tests to validate the fix |
| `jira-updater` | Comments on and transitions the Jira ticket |
| `pr-creator` | Opens a GitHub Pull Request |
| `gitlab-mr` | Opens a GitLab Merge Request |

The `Bug-fixer-agent` file is the master orchestrator — invoke it with a Jira ticket ID or URL to run the full 13-step pipeline.

---

## How to Use — By AI Tool

### Claude Code (Claude)

Agents live in `.claude/agents/`. Claude Code discovers them automatically.

1. Open this repo in Claude Code (CLI or IDE extension).
2. Simply tell Claude:
   ```
   Fix Jira bug PROJ-456
   ```
   or paste the full URL:
   ```
   Fix https://jiraeu.epam.com/browse/PROJ-456
   ```
3. Claude will load `Bug-fixer-agent` as the orchestrator and delegate to sub-agents step by step.

To invoke a single sub-agent directly:
```
Use the jira-fetcher agent to fetch PROJ-456
```

---

### GitHub Copilot (VS Code)

GitHub Copilot agents must live in **`.github/agents/`** (not `.claude/agents/`).

**Setup:**

1. Copy the agents directory to the Copilot location:
   ```bash
   cp -r .claude/agents .github/agents
   ```
2. Each agent file (`agent.md`) is picked up automatically by Copilot Chat when you use `@agent` syntax.

**Usage in Copilot Chat:**

```
@Bug-fixer-agent Fix Jira bug PROJ-456
```

Or invoke a sub-agent directly:
```
@jira-fetcher Fetch ticket PROJ-456
```

> Note: Copilot reads the `agent.md` inside each subfolder as the agent definition. The `Bug-fixer-agent` file (no subfolder) acts as the master — you may rename it to `Bug-fixer-agent/agent.md` if Copilot requires a consistent structure.

---

### Cursor

Agents in Cursor are defined as **Custom Modes** or referenced via `.cursorrules`.

1. Place agent markdown files anywhere accessible (`.claude/agents/` works).
2. In Cursor Chat, paste the contents of `Bug-fixer-agent` as a system prompt for a custom mode, or reference it with:
   ```
   Follow the instructions in .claude/agents/Bug-fixer-agent and fix PROJ-456
   ```

---

## Environment Setup (Required for All Tools)

1. Copy the example env file:
   ```bash
   cp .env.example .env
   ```

2. Fill in your credentials:
   ```
   JIRA_BASE_URL=https://jiraeu.epam.com
   JIRA_API_TOKEN=your_personal_access_token

   # GitHub repos
   GITHUB_TOKEN=ghp_your_token_here

   # GitLab repos (e.g. githyd.epam.com)
   GITLAB_TOKEN=glpat_your_token_here
   ```

3. Install Python dependencies:
   ```bash
   pip install -r .claude/agents/requirements.txt
   ```

4. Verify GitHub CLI auth (if using GitHub):
   ```bash
   gh auth status
   ```

---

## State File

The pipeline writes progress to `.bug-fix-state.json` in the repo root. This file:
- Tracks which step completed (`current_step`)
- Stores reproduction evidence, root cause, branch name, PR URL, etc.
- Allows resuming an interrupted run — just re-invoke the agent with the same ticket ID

**Never commit this file** — it is listed in `.gitignore`.

---

## Jira Workflow Rules

- The agent will transition tickets to **"In Review"** or **"Start Progress"** only.
- It will **never** mark a ticket as "Done" or "Resolved" — that is a human decision after PR review.
- A label `bug-fixer-agent` is added to every ticket touched by this pipeline.
