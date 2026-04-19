# ragUni — Manual Testing Report

**Date:** 2026-03-15
**Tester:** Claude (automated browser testing)
**Environment:** Frontend localhost:3000 (Next.js 16.1.6 dev), Backend localhost:8000 (FastAPI)

---

## Summary

| Category | Pass | Fail | Warnings |
|----------|------|------|----------|
| Registration | 3/4 | 1 | 1 |
| Login | 3/3 | 0 | 0 |
| Chat | 4/5 | 0 | 1 |
| Admin Panel | 3/3 | 0 | 1 |
| Auth Guards | 3/3 | 0 | 0 |
| Theme Toggle | 1/1 | 0 | 0 |
| i18n | 2/3 | 0 | 1 |
| **Security** | — | **2** | 1 |

**Total issues found: 8** (2 critical, 2 medium, 4 low)

---

## CRITICAL Issues

### CRIT-1: CSP blocks React hydration — ALL client-side JS non-functional

**Severity:** Critical (P0) — **FIXED during testing**
**Location:** `frontend/next.config.ts`, line 39
**Root cause:** `script-src 'self'` in the Content-Security-Policy header blocks the inline `<script>` tag that Next.js 16 injects to set `self.__next_r` (request ID for WebSocket connection). Without this variable, the `hydrate()` function throws `InvariantError` and React never attaches event handlers to the DOM.

**Symptoms:**
- All forms submit as plain HTML GET requests (default browser behavior)
- Passwords appear in URL query parameters (e.g., `?password=123`)
- No client-side validation works
- No API calls are made
- No interactive features function (theme toggle, language switch, chat)

**Fix applied:**
```typescript
const isDev = process.env.NODE_ENV === "development";
const scriptSrc = isDev
  ? "script-src 'self' 'unsafe-inline' 'unsafe-eval'"
  : "script-src 'self' 'unsafe-inline'";
```

**Recommendation:** For production, implement nonce-based CSP via Next.js middleware instead of `'unsafe-inline'`. Next.js 16 supports this natively.

---

### CRIT-2: Anyone can register as admin via API

**Severity:** Critical (P0)
**Location:** `backend/app/api/v1/auth.py` (register endpoint), `backend/app/models/user.py` (UserCreate)
**Root cause:** The `UserCreate` Pydantic model accepts `role: UserRole` which includes `admin`. The `/api/v1/auth/register` endpoint has no check to prevent self-assignment of the `admin` role.

**Reproduction:**
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"hacker@evil.com","password":"HackPass1","full_name":"Hacker","role":"admin","faculty":"Admin"}'
```
Returns HTTP 201 with `"role": "admin"`.

**Recommendation:** Create a separate `RegistrationRole` enum with only `student` and `teacher`, or add a validator that rejects `admin` in the register endpoint. Admin accounts should only be created via CLI/seed script or by existing admins.

---

## MEDIUM Issues

### MED-1: Validation error messages not localized (Zod schema)

**Severity:** Medium
**Location:** `frontend/src/lib/validations.ts` (Zod schema messages)
**Description:** When the UI is in Ukrainian, Zod validation errors display in English: "Invalid email format", "Password must be at least 8 characters". Other UI validation errors (from `useTranslations`) correctly show in Ukrainian: "Email є обов'язковим".

**Recommendation:** Pass localized messages to Zod schema or use `zod-i18n-map` integration with `next-intl`.

---

### MED-2: LocaleSwitcher component exists but is not rendered anywhere

**Severity:** Medium
**Location:** `frontend/src/components/layout/locale-switcher.tsx`
**Description:** The `LocaleSwitcher` component is implemented but not imported or used in any layout, header, or page. Users have no UI control to switch between English and Ukrainian. The only way to change locale is by manually setting the `locale` cookie.

**Recommendation:** Add `<LocaleSwitcher />` to the Header component next to the theme toggle button.

---

## LOW Issues

### LOW-1: Chat history sidebar doesn't update in real-time after sending a message

**Severity:** Low
**Location:** `frontend/src/hooks/use-chat.ts`, `frontend/src/components/layout/app-sidebar.tsx`
**Description:** After sending a chat message and receiving a response, the sidebar still shows "Немає попередніх чатів" (No previous chats). The new session only appears after a full page reload.

**Recommendation:** Call `refresh()` from `useChatHistory` after `sessionId` is received from the SSE stream, or use a shared state/context between chat and sidebar.

---

### LOW-2: Supported file formats mismatch between UI text and actual capability

**Severity:** Low
**Location:** `frontend/src/components/admin/document-upload.tsx`
**Description:** The upload area states "Підтримувані формати: PDF, DOCX, XLSX (до 10 МБ)" but the system also accepts TXT files (confirmed by existing `test_doc.txt` in the documents list). The frontend validation also allows TXT.

**Recommendation:** Update the UI description to include TXT, or remove TXT support if not intended.

---

### LOW-3: No visible success toast after registration

**Severity:** Low
**Location:** `frontend/src/components/auth/register-form.tsx`, line 99
**Description:** After successful registration, `toast.success(t("success"))` is called but the redirect to `/login` happens immediately. The toast may not be visible because the page navigates away before the toast renders, or the `<Toaster>` component may not be mounted on the auth layout.

**Recommendation:** Either delay the redirect slightly, or show a success message on the login page via query parameter.

---

### LOW-4: Frontend form uses GET method as fallback (pre-fix)

**Severity:** Low (resolved by CRIT-1 fix)
**Description:** The `<form>` elements don't specify `method="POST"`. When JavaScript fails (hydration error), they fall back to the browser's default GET method, exposing form data (including passwords) in URLs. While this is fixed by resolving CRIT-1, adding `method="POST"` as a defensive measure would prevent password exposure if hydration ever fails again.

**Recommendation:** Add `method="POST"` to all `<form>` elements as defense-in-depth.

---

## Passed Tests

### Registration
- [x] Registration form renders correctly with all fields (student: email, password, name, role, faculty, group, year)
- [x] Empty form submission shows validation error: "Email є обов'язковим"
- [x] Invalid email + short password shows per-field errors with red borders
- [x] Successful student registration redirects to /login

### Login
- [x] Login form renders with email/password fields
- [x] Invalid credentials show: "Невірна електронна пошта або пароль" (secure — doesn't reveal which field is wrong)
- [x] Successful login redirects to /chat with user info in header

### Chat
- [x] Empty state shows "Університетський асистент" with description
- [x] Message sent successfully, streaming response received
- [x] LLM responds in Ukrainian when context is Ukrainian
- [x] Source citations display with expandable document chunks ("Джерела (1)", file name, chunk text, metadata)
- [x] Chat session persists and loads correctly from history

### Admin Panel
- [x] Dashboard shows stats cards: Users (5), Pending Teachers (0), Documents (1), Chunks (1)
- [x] Document management: table with file info, upload zone, delete button
- [x] User management: table with role dropdowns, block buttons, status badges

### Auth Guards
- [x] Unauthenticated user → redirect to /login from /chat
- [x] Student user → redirect to /chat from /admin
- [x] Student user → redirect to /chat from /admin/users

### Theme
- [x] Dark/light toggle works, icon changes (moon ↔ sun), persists across pages

### i18n
- [x] Ukrainian locale renders correctly across all pages
- [x] English locale renders correctly when cookie is set to `en`

---

## Test Environment Notes

- Next.js 16.1.6 with Turbopack (dev mode)
- React 19.2.3
- Backend: FastAPI with MongoDB Atlas
- Browser: Chrome (automated via Claude in Chrome)
