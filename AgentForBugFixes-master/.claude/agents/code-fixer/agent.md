---
name: code-fixer
description: Applies the minimal code change required to fix the root cause identified by bug-investigator. Follows existing code style and patterns without refactoring or reformatting.
when_to_use: Use this skill as Step 5 of the bug-fixing workflow, after root cause is documented and the fix plan is approved (Step 4 self-check passed).
---

# Code Fixer Skill

## Purpose
Apply a precise, minimal fix to the files identified by `bug-investigator`. The change must address the root cause — not just the symptom — while leaving all unrelated code untouched.

## Input
Read `.bug-fix-state.json` to get: `root_cause`, `files_to_change`, `bug_type`, `investigation_notes`.

## Cardinal Rules (NEVER BREAK)
1. **Minimal change** — change the fewest lines possible. If one line fixes it, change one line.
2. **Match existing style** — use the same indentation, brace style, naming conventions, and import ordering already present in the file.
3. **No refactoring** — do not rename variables, extract methods, or restructure code that is not part of the bug.
4. **No formatting changes** — do not re-indent, add/remove blank lines, or reorder imports in unaffected sections.
5. **No new dependencies** — do not add new Maven dependencies to `pom.xml` or new npm packages to `package.json` unless the fix is impossible without them (requires explicit user approval).
6. **Edit only `files_to_change`** — do not touch any file not listed in the state.

## Backend Spring Boot Patterns

### Null Pointer Exception (NPE)
```java
// Before (unsafe)
String value = entity.getField().getValue();

// After (null-safe)
String value = entity.getField() != null ? entity.getField().getValue() : null;
// Or with Optional:
String value = Optional.ofNullable(entity.getField())
                       .map(Field::getValue)
                       .orElse(null);
```

### JPA / Transactional Issues
```java
// Missing @Transactional on a write method
@Transactional
public void updateEntity(Long id, String newValue) { ... }

// Lazy loading outside transaction — add fetch or widen @Transactional scope
@Transactional(readOnly = true)
public EntityDto getWithChildren(Long id) {
    Entity e = repo.findById(id).orElseThrow();
    e.getChildren().size(); // force load inside transaction
    return mapper.toDto(e);
}
```

### REST API / Response Issues
```java
// Wrong HTTP status — fix ResponseEntity
return ResponseEntity.ok(result);          // 200
return ResponseEntity.created(uri).build(); // 201
return ResponseEntity.noContent().build(); // 204
return ResponseEntity.notFound().build();  // 404
```

### Exception Handling
```java
// Add specific exception handler in @ControllerAdvice or existing handler class
@ExceptionHandler(ResourceNotFoundException.class)
public ResponseEntity<ErrorResponse> handleNotFound(ResourceNotFoundException ex) {
    return ResponseEntity.status(HttpStatus.NOT_FOUND)
                         .body(new ErrorResponse(ex.getMessage()));
}
```

## Frontend React Patterns

### State Update Issues
```tsx
// Before (mutating state directly)
state.items.push(newItem);

// After (immutable update)
setState(prev => ({ ...prev, items: [...prev.items, newItem] }));
```

### API Call / Axios Issues
```tsx
// Missing error handling
try {
  const response = await axios.get('/api/resource');
  setData(response.data);
} catch (error) {
  console.error('Failed to fetch resource:', error);
  setError(error.response?.data?.message || 'An error occurred');
}
```

### useEffect Dependency Issues
```tsx
// Before (missing dependency)
useEffect(() => {
  fetchData(userId);
}, []); // eslint-disable-line

// After (correct dependency)
useEffect(() => {
  fetchData(userId);
}, [userId]);
```

### Conditional Render / Undefined Check
```tsx
// Before (crashes when data is undefined)
return <div>{data.name}</div>;

// After (safe render)
return <div>{data?.name ?? 'Loading...'}</div>;
```

## Fix Process

1. Read `.bug-fix-state.json` for `files_to_change` and `root_cause`.
2. Read each target file in full using the Read tool.
3. Identify the exact lines that implement the fix.
4. Apply the fix using the Edit tool (NOT Write — preserve all surrounding code).
5. Re-read the edited file to confirm the change looks correct in context.
6. Update `.bug-fix-state.json`:
   - Increment `fix_attempts` by 1.
   - Add `fix_description`: one sentence describing what was changed and why.
   - Add `files_changed`: list of files actually edited (may be subset of `files_to_change`).
7. Proceed to Step 6 (Add/Update Tests).

## Self-Check Before Applying Fix
Answer all three before proceeding:
- [ ] Does this change address the `root_cause` in `.bug-fix-state.json`?
- [ ] Is this the minimal change? Could it be smaller?
- [ ] Could this change break any existing functionality?

If any answer is uncertain, re-read the relevant code before proceeding.
