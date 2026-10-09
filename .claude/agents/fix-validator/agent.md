---
name: fix-validator
description: Validates the applied fix by running the relevant test suite and type/lint checks, then documents the outcome in .bug-fix-state.json.
when_to_use: Use this skill as Step 7 of the bug-fixing workflow, after code-fixer has applied the change and tests have been added or updated (Step 6).
---

# Fix Validator Skill

## Purpose
Confirm that the fix works correctly and has not broken any existing functionality. Run the full relevant test suite and record pass/fail results in `.bug-fix-state.json`.

## Input
Read `.bug-fix-state.json` to get: `bug_type`, `files_changed`, `fix_description`, `fix_attempts`.

## Backend Validation (step-epamin-develop)

### Run all tests
```bash
cd step-epamin-develop && ./mvnw test
```

### Run a specific test class
```bash
cd step-epamin-develop && ./mvnw test -Dtest="ClassName" -pl .
```

### Run a specific test method
```bash
cd step-epamin-develop && ./mvnw test -Dtest="ClassName#methodName" -pl .
```

### Compile check only (fast sanity check)
```bash
cd step-epamin-develop && ./mvnw compile -q
```

### Run tests for a specific module/package
```bash
cd step-epamin-develop && ./mvnw test -Dtest="com.top.talent.management.service.**" -pl .
```

## Frontend Validation (step-ui-develop/step-ui-develop)

### Run all tests (non-interactive)
```bash
cd step-ui-develop/step-ui-develop && npm test -- --watchAll=false
```

### Run a specific test file
```bash
cd step-ui-develop/step-ui-develop && npm test -- --watchAll=false --testPathPattern="ComponentName"
```

### Run tests matching a description
```bash
cd step-ui-develop/step-ui-develop && npm test -- --watchAll=false -t "should render correctly"
```

### TypeScript type check
```bash
cd step-ui-develop/step-ui-develop && npx tsc --noEmit
```

### ESLint check
```bash
cd step-ui-develop/step-ui-develop && npx eslint src --ext .ts,.tsx --max-warnings=0
```

## Validation Process

1. Read `.bug-fix-state.json` for `bug_type` and `files_changed`.
2. Run the appropriate validation commands above based on `bug_type`.
3. Capture the full output (pass count, failure messages, error details).
4. Update `.bug-fix-state.json`:
   - Set `test_results` to `"passed"` or `"failed: <brief reason>"`.
   - Add `validation_output`: key lines from the test output.
5. **If passed** → proceed to Step 8 (`jira-updater`).
6. **If failed** → apply the 3-attempt retry rule below.

## 3-Attempt Retry Rule

When tests fail after applying a fix:
1. Increment `fix_attempts` in `.bug-fix-state.json`.
2. Return to `code-fixer` (Step 5) and attempt a revised fix.
3. Re-run validation (Step 7).

If `fix_attempts` reaches **3** and tests are still failing:
- **STOP immediately.**
- Do NOT make further code changes.
- Report to the user with:
  - All 3 fix strategies attempted
  - The exact test failure output
  - Your current understanding of why the fix is non-trivial
  - A request for human review

## Adding Regression Tests (Step 6 guidance)

After applying the fix but before running validation, add a test that would have caught this bug.

### JUnit (Backend) — in `step-epamin-develop/src/test/java/...`
```java
@Test
void shouldNotThrowWhenFieldIsNull() {
    // Arrange
    Entity entity = new Entity();
    entity.setField(null); // the condition that triggered the bug

    // Act + Assert
    assertDoesNotThrow(() -> service.processEntity(entity));
}

@Test
void shouldReturn404WhenResourceNotFound() {
    // Arrange
    when(repository.findById(999L)).thenReturn(Optional.empty());

    // Act
    ResponseEntity<?> response = controller.getResource(999L);

    // Assert
    assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
}
```

### Jest / React Testing Library (Frontend) — in `step-ui-develop/step-ui-develop/src/...`
```tsx
test('renders without crashing when data is undefined', () => {
  render(<MyComponent data={undefined} />);
  expect(screen.getByText('Loading...')).toBeInTheDocument();
});

test('shows error message on API failure', async () => {
  server.use(
    rest.get('/api/resource', (req, res, ctx) => res(ctx.status(500)))
  );
  render(<MyComponent />);
  expect(await screen.findByText(/error occurred/i)).toBeInTheDocument();
});
```

Place tests adjacent to or in the same package/directory as the code under test. Follow the naming conventions already used in the project.

## Success Criteria
Validation is considered **passed** when:
- All pre-existing tests pass (no regressions).
- The new regression test passes.
- TypeScript compiles without errors (frontend).
- No new lint errors introduced (frontend).
