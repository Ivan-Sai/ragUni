import NextAuth from "next-auth";
import type { NextAuthConfig } from "next-auth";
import Credentials from "next-auth/providers/credentials";
import { authApi } from "@/lib/api";
import { API_BASE_URL, API_PREFIX } from "@/lib/env";

declare module "next-auth" {
  interface Session {
    user: {
      id: string;
      email: string;
      name: string;
      role: string;
      faculty: string | null;
    };
    accessToken: string;
    error?: string;
  }

  interface User {
    id: string;
    email: string;
    name: string;
    role: string;
    faculty: string | null;
    accessToken: string;
    refreshToken: string;
  }
}

declare module "@auth/core/jwt" {
  interface JWT {
    role: string;
    faculty: string | null;
    accessToken: string;
    refreshToken: string;
    accessTokenExpires: number;
    error?: string;
  }
}

export const authOptions: NextAuthConfig = {
  providers: [
    Credentials({
      name: "Credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) {
          console.error("[auth] Missing email or password in credentials");
          return null;
        }

        try {
          const tokens = await authApi.login({
            email: credentials.email as string,
            password: credentials.password as string,
          });

          const user = await authApi.getMe(tokens.access_token);

          return {
            id: user.id,
            email: user.email,
            name: user.full_name,
            role: user.role,
            faculty: user.faculty,
            accessToken: tokens.access_token,
            refreshToken: tokens.refresh_token,
          };
        } catch (error) {
          console.error("[auth] authorize failed:", error instanceof Error ? error.message : error);
          return null;
        }
      },
    }),
  ],
  session: {
    strategy: "jwt",
  },
  pages: {
    signIn: "/login",
  },
  callbacks: {
    async jwt({ token, user }) {
      // Initial sign in — store tokens from the user object
      if (user) {
        token.role = user.role;
        token.faculty = user.faculty;
        token.accessToken = user.accessToken;
        token.refreshToken = user.refreshToken;
        // Set expiry to 25 minutes from now (access token is 30 min)
        token.accessTokenExpires = Date.now() + 25 * 60 * 1000;
      }

      // Return token if not expired
      if (Date.now() < (token.accessTokenExpires as number)) {
        return token;
      }

      // Access token expired — try to refresh
      try {
        const response = await fetch(
          `${API_BASE_URL}${API_PREFIX}/auth/refresh`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh_token: token.refreshToken }),
          }
        );

        if (!response.ok) {
          throw new Error("Refresh failed");
        }

        const data = await response.json();
        return {
          ...token,
          accessToken: data.access_token,
          accessTokenExpires: Date.now() + 25 * 60 * 1000,
        };
      } catch {
        // Refresh failed — mark session as expired
        return { ...token, error: "RefreshAccessTokenError" };
      }
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.id = token.sub ?? session.user.id;
        session.user.email =
          (token.email as string | undefined) ?? session.user.email;
        session.user.name =
          (token.name as string | undefined) ?? session.user.name;
        session.user.role = token.role as string;
        session.user.faculty = token.faculty as string;
      }
      session.accessToken = token.accessToken as string;
      session.error = token.error as string | undefined;
      return session;
    },
  },
};

export const { handlers, signIn, signOut, auth } = NextAuth(authOptions);
