---
name: bug-investigator
description: Investigates the root cause of a reproduced bug using code search, git blame, and structured 5-Whys analysis. Produces a documented root cause without making any code changes.
when_to_use: Use this skill as Step 3 of the bug-fixing workflow, after the bug has been successfully reproduced. Never use before reproduction is confirmed.
---

# Bug Investigator Skill

## Purpose
Find the precise root cause of the bug through systematic code exploration. Document findings thoroughly so the `code-fixer` skill can make a targeted, minimal fix.

## Input
Read `.bug-fix-state.json` to get: `description`, `reproduction_notes`, `bug_type`.

## Code Search — Backend (step-epamin-develop)

Search Java source with `rg` (ripgrep):
```bash
# Search for a method or class name
rg "methodName" step-epamin-develop/src --type java

# Search for an exception class
rg "NullPointerException|IllegalArgumentException" step-epamin-develop/src --type java -l

# Search for an endpoint path
rg '"/api/some/path"' step-epamin-develop/src --type java -n

# Search for a service or repository
rg "EmployeeRepository|UserService" step-epamin-develop/src --type java -n

# Search for a specific annotation
rg "@Transactional|@Scheduled" step-epamin-develop/src --type java -n

# Context around a match (5 lines before/after)
rg "somePattern" step-epamin-develop/src --type java -C 5
```

## Code Search — Frontend (step-ui-develop/step-ui-develop)

Search TypeScript/TSX/JS source with `rg`:
```bash
# Search for a component or hook name
rg "ComponentName|useMyHook" step-ui-develop/step-ui-develop/src --type ts --type tsx

# Search for an API call path
rg '"/api/some/path"' step-ui-develop/step-ui-develop/src -n

# Search for Redux action or slice
rg "setEmployee|fetchUser" step-ui-develop/step-ui-develop/src --type ts -n

# Search for Axios usage
rg "axios\.(get|post|put|delete)" step-ui-develop/step-ui-develop/src -n

# Search across JS files too
rg "componentDidCatch|useEffect" step-ui-develop/step-ui-develop/src -n
```

## Git Blame
Once the suspicious file and line are identified, use git blame to understand when a change was introduced:
```bash
# Blame a specific file
git -C step-epamin-develop blame src/main/java/com/top/talent/management/service/impl/EmployeeServiceImpl.java

# Blame a specific line range
git -C step-epamin-develop blame -L 45,65 src/main/java/com/top/talent/management/service/impl/EmployeeServiceImpl.java

# Show the commit that last changed a line
git log --follow -p step-epamin-develop/src/main/java/com/top/talent/management/service/impl/EmployeeServiceImpl.java | head -80

# Frontend
git blame step-ui-develop/step-ui-develop/src/components/SomeComponent.tsx
```

## 5-Whys Analysis
Apply the 5-Whys technique to reach the true root cause:

```
Symptom: <what the user reported — from ticket description>

Why 1: <why did that symptom occur? — from reproduction>
Why 2: <why did that happen? — from code search>
Why 3: <why was it written that way? — from git blame / commit context>
Why 4: <what condition made this surface now? — data, config, or code change>
Why 5 (Root Cause): <the single specific line/condition that must be fixed>
```

Stop at the depth where the answer is actionable (a specific line or logic error). Document the full chain.

## Investigation Process

1. Extract key terms from `reproduction_notes` (error class, method name, endpoint path, component name).
2. Search backend source (`step-epamin-develop/src`) with at least 3 distinct `rg` queries.
3. Search frontend source (`step-ui-develop/step-ui-develop/src`) if `bug_type` is `frontend` or `both`.
4. Identify the 1–3 files most likely responsible.
5. Read the relevant files in full using the Read tool.
6. Run `git blame` on the suspicious lines.
7. Apply 5-Whys to document root cause.
8. Update `.bug-fix-state.json`:
   - Set `root_cause` to a concise one-sentence description.
   - Set `files_to_change` to the list of files that need modification.
   - Add `investigation_notes` with the full 5-Whys chain.
9. Proceed to Step 4 (Plan Fix).

## Important Rules
- **NEVER modify any source files** during investigation.
- **NEVER assume** the root cause without evidence from the code.
- If multiple possible causes exist, list all of them and reason about which is most likely.
- If you cannot determine root cause after exhaustive search, STOP and report to the user with all findings gathered so far.
- Read the actual code — do not rely on memory or assumptions about framework behavior.
