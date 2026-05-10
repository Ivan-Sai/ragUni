import { auth } from "@/lib/auth";
import { NextResponse, type NextRequest } from "next/server";

/**
 * Edge middleware — two responsibilities per request:
 *
 *   1. Auth gate: server-side role / login check before any HTML
 *      is rendered. Without this, role checks would only happen
 *      client-side via useSession() and an unauthenticated user
 *      would briefly see the admin shell before the redirect.
 *
 *   2. CSP nonce: mints a per-request random nonce, attaches it
 *      to the request headers (so server components can read it
 *      via `headers().get("x-nonce")` and stamp it onto inline
 *      scripts), and sets a strict CSP header that whitelists
 *      ONLY scripts carrying that nonce. This eliminates the
 *      `'unsafe-inline'` / `'unsafe-eval'` script directives that
 *      otherwise neuter the CSP.
 *
 * Next.js auto-loads this file because it sits at `src/middleware.ts`.
 * Renaming or moving it silently disables every protection below.
 */

const isDev = process.env.NODE_ENV !== "production";

function generateNonce(): string {
  // 16 random bytes → base64 ~24 chars, enough entropy for CSP and
  // cheap on the edge. Web Crypto is always available in the Edge
  // runtime; no Node `crypto` shim needed.
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

function buildCsp(nonce: string, apiOrigin: string): string {
  // Script directive:
  //  - 'self' covers our own bundles
  //  - nonce-XXXX covers Next.js inline runtime scripts (each marked
  //    with the same nonce by Next 15 when NEXT_NONCE is exposed)
  //  - 'strict-dynamic' lets nonce'd scripts spawn descendants without
  //    listing each CDN, which is the modern recommendation
  //  - dev needs unsafe-eval for React Refresh; we keep it off in prod
  const scriptSrc = [
    "script-src",
    "'self'",
    `'nonce-${nonce}'`,
    "'strict-dynamic'",
    isDev ? "'unsafe-eval'" : "",
  ]
    .filter(Boolean)
    .join(" ");

  // Tailwind v4 + shadcn inject inline <style>, so we keep
  // 'unsafe-inline' on style-src (style XSS is much narrower than
  // script XSS — no JS execution, no token exfiltration).
  return [
    "default-src 'self'",
    scriptSrc,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    `connect-src 'self' ${apiOrigin}`,
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "object-src 'none'",
    "form-action 'self'",
    isDev ? "" : "upgrade-insecure-requests",
  ]
    .filter(Boolean)
    .join("; ");
}

function applySecurityHeaders(req: NextRequest, res: NextResponse): NextResponse {
  const nonce = generateNonce();
  const apiOrigin =
    process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  // Make the nonce visible to server components via headers().
  res.headers.set("x-nonce", nonce);
  res.headers.set("Content-Security-Policy", buildCsp(nonce, apiOrigin));
  res.headers.set("X-Content-Type-Options", "nosniff");
  res.headers.set("X-Frame-Options", "DENY");
  res.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  res.headers.set(
    "Permissions-Policy",
    "camera=(), microphone=(), geolocation=()"
  );
  if (!isDev) {
    res.headers.set(
      "Strict-Transport-Security",
      "max-age=31536000; includeSubDomains"
    );
  }
  return res;
}

export default auth((req) => {
  const { nextUrl } = req;
  const isAuthenticated = Boolean(req.auth);
  const role = req.auth?.user?.role;

  const isAuthPage =
    nextUrl.pathname.startsWith("/login") ||
    nextUrl.pathname.startsWith("/register") ||
    nextUrl.pathname.startsWith("/forgot-password") ||
    nextUrl.pathname.startsWith("/reset-password");

  const isApiRoute = nextUrl.pathname.startsWith("/api");

  // Don't intercept API routes — NextAuth handlers and any other
  // /api/* endpoints handle their own auth.
  if (isApiRoute) {
    return NextResponse.next();
  }

  // Redirect authenticated users away from auth pages.
  if (isAuthPage && isAuthenticated) {
    return applySecurityHeaders(
      req,
      NextResponse.redirect(new URL("/chat", nextUrl))
    );
  }

  // Redirect unauthenticated users to login (except for the public
  // landing page at /).
  if (!isAuthPage && !isAuthenticated && nextUrl.pathname !== "/") {
    return applySecurityHeaders(
      req,
      NextResponse.redirect(new URL("/login", nextUrl))
    );
  }

  // Admin-route protection — only admin role can access /admin/*.
  if (nextUrl.pathname.startsWith("/admin") && role !== "admin") {
    return applySecurityHeaders(
      req,
      NextResponse.redirect(new URL("/chat", nextUrl))
    );
  }

  return applySecurityHeaders(req, NextResponse.next());
});

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
