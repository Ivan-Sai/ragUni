/**
 * Browser-side Sentry initialisation.
 *
 * The `@sentry/nextjs` SDK is treated as an *optional* dependency so the
 * app builds and runs even when it is not installed — useful in CI and
 * in teaching environments. If `NEXT_PUBLIC_SENTRY_DSN` is set we load
 * the SDK via dynamic `import()` so no code is bundled when Sentry is
 * disabled.
 */

const DSN = process.env.NEXT_PUBLIC_SENTRY_DSN;
const ENV = process.env.NEXT_PUBLIC_ENVIRONMENT ?? "development";
const RELEASE = process.env.NEXT_PUBLIC_RELEASE;

let initialised = false;

export async function initSentryClient(): Promise<void> {
  if (initialised || !DSN || typeof window === "undefined") {
    return;
  }
  try {
    const Sentry = await import(
      /* webpackChunkName: "sentry" */ "@sentry/nextjs"
    );
    Sentry.init({
      dsn: DSN,
      environment: ENV,
      release: RELEASE,
      tracesSampleRate: 0.1,
      // Never ship question text or user emails to Sentry.
      sendDefaultPii: false,
    });
    initialised = true;
  } catch {
    // Package is not installed — silently skip. Intentional: the app
    // must keep working without Sentry in development.
  }
}
