# Dependency notes

Brief rationale for any dependency decision that is not obvious from the
package name. The rest of the stack is pinned in
[`backend/requirements.txt`](../backend/requirements.txt) and
[`frontend/package.json`](../frontend/package.json).

## Backend

* **`motor` + `pymongo` must match.** Motor is an async driver built on
  top of pymongo — upgrading one without the other breaks connection
  pooling. Always bump them together.
* **`langchain-*` packages share a release train.** The 1.x ecosystem
  pins `core`, `community`, `mongodb`, `openai`, and `text-splitters`
  together; mixing majors produces opaque import errors. When upgrading,
  update all six lines in `requirements.txt` at once.
* **`sentry-sdk[fastapi]` and `prometheus-fastapi-instrumentator`** are
  runtime-optional: the app checks for the module at startup and logs a
  warning if missing. They are listed as pinned dependencies so CI
  installs them and the production image is fully instrumented.
* **`python-magic-bin`** is Windows-only. On Linux containers install
  `python-magic` + `libmagic1` via the system package manager instead.
  This is handled in `backend/Dockerfile`.

## Frontend

### `next-auth` v5 is on a public beta release

We ship `next-auth: ^5.0.0-beta.30` (Auth.js v5) deliberately — the
final `5.0.0` tag has not been published yet, but v4 is in maintenance
and lacks first-class App Router / React Server Components support that
the rest of the project relies on.

**Risk assessment:**

| Concern                 | Mitigation                                                     |
| ----------------------- | -------------------------------------------------------------- |
| Breaking API changes    | Beta patch releases have been additive for 6+ months; we pin the minor range and read the changelog before upgrading. |
| Security disclosures    | We track `@auth/core` CVE advisories; the project is widely deployed in beta and patched quickly. |
| Future stable upgrade   | When 5.0.0 ships, only `package.json` and a brief smoke test of the login → refresh flow are expected to change. |
| No long-term support    | v4 → v5 migration is already complete in our codebase, so falling back is no longer an option without a rewrite. |

**Acceptance criteria to consider a stable release:** both `next-auth`
and `@auth/core` have a non-pre-release version matching the current
beta's API, and the
[GitHub Auth.js release notes](https://github.com/nextauthjs/next-auth/releases)
mark the transition as a major release.

### Optional: `@sentry/nextjs`

The `frontend/src/lib/sentry.ts` helper loads `@sentry/nextjs` via a
dynamic `import()`. The package is **not** currently listed in
`package.json` — add it (and optionally wrap the build with
`withSentryConfig`) only when enabling Sentry in a specific deployment.
The rest of the app is unaffected by its absence.

## Upgrade cadence

* Security patches: within 7 days of disclosure.
* Minor bumps: monthly, in a dedicated PR that re-runs `pytest` +
  `npm run build`.
* Major bumps: case by case, with a dedicated ADR under `docs/`.
