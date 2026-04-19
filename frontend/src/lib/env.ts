/**
 * Runtime environment configuration.
 *
 * Validated eagerly so a missing NEXT_PUBLIC_API_URL fails the app at the
 * first import rather than silently falling back to a developer URL in
 * production — which would leak configuration mistakes to real users.
 */

const RAW_API_URL = process.env.NEXT_PUBLIC_API_URL;

function assertApiUrl(value: string | undefined): string {
  if (!value || value.trim() === "") {
    throw new Error(
      "NEXT_PUBLIC_API_URL is not configured. Set it in .env.local " +
        "(development) or in the deployment environment (production)."
    );
  }
  try {
    // Validate that it parses as a URL so typos like "localhost:8000"
    // (missing scheme) are caught at startup instead of at request time.
    new URL(value);
  } catch {
    throw new Error(
      `NEXT_PUBLIC_API_URL is not a valid URL: "${value}". ` +
        "It must include scheme and host, e.g. https://api.example.com"
    );
  }
  return value.replace(/\/+$/, "");
}

export const API_BASE_URL: string = assertApiUrl(RAW_API_URL);
export const API_PREFIX = "/api/v1" as const;
