# Test-Driven Development (TDD)

## Core Principle

Write the test first. Watch it fail. Write minimal code to pass.

**NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST.**

## When to Use

**Always (backend):**
- New features (auth, RBAC, endpoints, services)
- Bug fixes
- Refactoring existing code

**Frontend — TDD only for logic, NOT for UI components:**
- **TDD:** API clients, custom hooks (useChat, useChatHistory), utility functions
- **NO TDD:** React components, pages, layouts — UI is tested visually, not with unit tests
- Reason: component tests require heavy mocking (next-auth, router, markdown), test mocks not real behavior, and break on any markup change

**Exceptions (ask the user):**
- Throwaway prototypes
- Configuration files
- Docker/infrastructure setup

## Red-Green-Refactor Cycle

### 1. RED — Write Failing Test

```bash
pytest tests/path/to/test.py::test_name -v
```

- One test, one behavior
- Clear descriptive name
- Real code, no mocks unless unavoidable (external APIs, DB)
- Verify it **fails for the expected reason** (missing feature, not typo)

### 2. GREEN — Minimal Code

- Write the **simplest** code to pass the test
- Don't add features beyond what the test requires
- Don't refactor yet

```bash
pytest tests/path/to/test.py::test_name -v
```

- Verify it **passes**
- Verify **all other tests still pass**

### 3. REFACTOR — Clean Up

- Remove duplication, improve names, extract helpers
- Keep all tests green
- Don't add new behavior

### 4. Repeat

Next failing test for next behavior.

## Iron Rules

1. **Code before test? Delete it. Start over.**
2. **Test passes immediately? You're testing existing behavior. Fix the test.**
3. **Never skip verification steps** — always run tests after RED and GREEN.
4. **Mocks only for external dependencies** (MongoDB, Deepseek API, external HTTP).
5. **Test real behavior, not mock behavior.**

## Testing Anti-Patterns to Avoid

| Anti-Pattern | Fix |
|---|---|
| Asserting on mock elements | Test real component behavior |
| Test-only methods in production classes | Move to test utilities |
| Mocking without understanding side effects | Understand dependencies first, mock minimally |
| Incomplete mock data | Mirror real data structures completely |
| Tests as afterthought | TDD — tests first, always |

## Project-Specific Guidelines

### What to Mock
- MongoDB operations → use `mongomock` or async mock
- Deepseek API calls → mock HTTP responses
- FastEmbed embeddings → return fixed vectors for speed
- File uploads → use `UploadFile` with `BytesIO`

### What NOT to Mock
- Pydantic model validation
- Text chunking logic
- Request/response serialization
- RBAC permission checks (test real logic)
- JWT token generation/validation (test real crypto)

### Test Structure
```
tests/
├── conftest.py          # Shared fixtures (app client, mock DB, test user)
├── unit/
│   ├── test_auth.py     # JWT, password hashing
│   ├── test_rbac.py     # Role-based access control
│   ├── test_models.py   # Pydantic model validation
│   └── test_chunking.py # Text chunking logic
├── api/
│   ├── test_auth_api.py     # /auth endpoints
│   ├── test_chat_api.py     # /chat endpoints
│   ├── test_documents_api.py # /documents endpoints
│   └── test_admin_api.py    # /admin endpoints
└── services/
    ├── test_document_parser.py
    ├── test_vector_store.py
    └── test_llm.py
```

### Running Tests
```bash
# All tests
pytest -v

# Specific file
pytest tests/unit/test_auth.py -v

# Specific test
pytest tests/unit/test_auth.py::test_jwt_token_valid -v

# With coverage
pytest --cov=app --cov-report=term-missing -v
```

## Common Rationalizations — Don't Fall For These

| Excuse | Reality |
|---|---|
| "Too simple to test" | Simple code breaks. Test takes 30 seconds. |
| "I'll test after" | Tests passing immediately prove nothing. |
| "Need to explore first" | Fine. Throw away exploration, then TDD. |
| "TDD will slow me down" | TDD is faster than debugging. |

## Verification Checklist

Before marking work complete:
- [ ] Every new function/method has a test
- [ ] Watched each test fail before implementing
- [ ] Each test failed for expected reason
- [ ] Wrote minimal code to pass each test
- [ ] All tests pass
- [ ] Tests use real code (mocks only for external deps)
- [ ] Edge cases covered
