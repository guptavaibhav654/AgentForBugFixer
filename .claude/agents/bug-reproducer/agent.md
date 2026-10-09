---
name: bug-reproducer
description: Attempts to reproduce the bug described in .bug-fix-state.json by running the application locally and following the steps to trigger the failure.
when_to_use: Use this skill as Step 2 of the bug-fixing workflow, immediately after jira-fetcher. Do NOT skip reproduction — if a bug cannot be reproduced, the fix cannot be verified.
---

# Bug Reproducer Skill

## Purpose
Reproduce the bug in a controlled local environment before any investigation or code change. This confirms the bug is real, defines the failure signature, and provides a baseline to verify the fix later.

## Input
Read `.bug-fix-state.json` to get:
- `ticket_id`, `description`, `comments`, `attachments`
- The structured bug-report sections parsed by `jira-fetcher`:
  - `reproduction_steps` — explicit steps if provided
  - `current_behavior` — what the system does today (the bug)
  - `expected_behavior` — what it should do
  - `actual_result` — concrete observed output (HTTP code, error, UI state)
  - `expected_result` — concrete correct output
  - `acceptance_criteria` — checks the fix must satisfy

These sections are the reproduction script. Read all of them before starting — they often clarify ambiguity in the title or description.

## Detection: Backend vs Frontend

Classify the bug by examining the description keywords:

| Signal | Classification |
|---|---|
| Stack trace, `NullPointerException`, `500`, SQL error, JPA, Hibernate | **backend** |
| UI crash, React error, blank screen, Redux state, Axios, CORS, `401`/`403` | **frontend** |
| Both types of signals present | **both** |

## Backend Reproduction (step-epamin-develop)

### 1. Start the application
```bash
cd step-epamin-develop && ./mvnw spring-boot:run
```
Wait for `Started ... Application in X seconds`.

### 2. Reproduce via API call
Use `curl`, Postman, or HTTPie with the exact request described in the Jira ticket:
```bash
curl -X POST http://localhost:8080/api/... \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{ ...payload from ticket... }'
```

### 3. Check logs
Look for stack traces, exceptions, or unexpected status codes in the Spring Boot console output.

### 4. Run unit test if one is cited
```bash
cd step-epamin-develop && ./mvnw test -Dtest="TestClassName#methodName" -pl .
```

## Frontend Reproduction (step-ui-develop/step-ui-develop)

### 1. Install dependencies (first time only)
```bash
cd step-ui-develop/step-ui-develop && npm install
```

### 2. Start the dev server
```bash
cd step-ui-develop/step-ui-develop && npm start
```
Wait for `Compiled successfully` in the terminal.

### 3. Reproduce in browser
Open the URL shown (usually `http://localhost:3000`) and follow the exact UI steps described in the ticket. Open DevTools → Console and Network tabs.

### 4. Check for JS errors
Note any `TypeError`, `Uncaught Error`, failed network requests (4xx/5xx), or blank component renders.

## Process Steps

1. **Read** the structured sections (`reproduction_steps`, `current_behavior`, `expected_behavior`, `actual_result`, `expected_result`, `acceptance_criteria`) plus the full description and comments from `.bug-fix-state.json`.
2. **Classify** as backend, frontend, or both.
3. **Start** the relevant application(s). If startup fails on missing env vars, DB, or auth → STOP and surface the blockers; do not fall back to code-only reasoning.
4. **Follow** the reproduction steps exactly. Use `actual_result` and `expected_result` as the pass/fail oracle — your reproduction is successful only when you observe `actual_result` (the bug), not `expected_result`.
5. **Observe** and record the failure signature with concrete evidence: HTTP status code, response body, stack trace, screenshot path, DB row state, log line.
6. **Update** `.bug-fix-state.json`:
   - Set `reproduced: true` on success.
   - Add a `reproduction_evidence` key — concrete output proving the bug occurred (not a paraphrase).
   - Set `bug_type` to `"backend"`, `"frontend"`, or `"both"`.
7. **Proceed** to `bug-investigator` skill (Step 3) ONLY if `reproduced == true`. If not, STOP.

## 3-Attempt Failure Rule
If the bug cannot be reproduced after **3 distinct attempts** (varying inputs, environment, or approach), STOP and report back to the user with:
- What was attempted
- What was observed instead
- A request for clarification (missing steps, environment-specific data, credentials needed)

Do NOT guess or fabricate a reproduction. Do NOT proceed to investigation without a confirmed reproduction.

## Notes
- Check `.tmp/attachments/<ticket_id>/` for screenshots or log files attached to the ticket.
- If the bug requires specific test data (user IDs, database records), ask the user before proceeding.
- Do NOT modify any source files during reproduction.
