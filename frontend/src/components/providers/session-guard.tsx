"use client";

import { useEffect } from "react";
import { signOut, useSession } from "next-auth/react";

/**
 * Watches the active session for the `RefreshAccessTokenError` sentinel
 * set by the NextAuth jwt callback when refreshing the access token
 * fails (e.g. the refresh token was revoked, the backend rotated its
 * signing secret, or the user was blocked by an admin).
 *
 * When the error appears we sign the user out and bounce them to the
 * login screen. Without this, expired sessions silently remain
 * "logged in" from the client's perspective while every API call
 * returns 401 and the UI renders empty data blocks.
 */
export function SessionGuard({ children }: { children: React.ReactNode }) {
  const { data: session, status } = useSession();

  useEffect(() => {
    if (status !== "authenticated") return;
    if (session?.error === "RefreshAccessTokenError") {
      void signOut({ callbackUrl: "/login" });
    }
  }, [session, status]);

  return <>{children}</>;
}
