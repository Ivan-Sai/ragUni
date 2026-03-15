import { auth } from "@/lib/auth";
import { NextResponse } from "next/server";

export const proxy = auth((req) => {
  const { nextUrl } = req;
  const isAuthenticated = !!req.auth;

  const isAuthPage =
    nextUrl.pathname.startsWith("/login") ||
    nextUrl.pathname.startsWith("/register");

  const isApiRoute = nextUrl.pathname.startsWith("/api");

  // Don't intercept API routes
  if (isApiRoute) {
    return NextResponse.next();
  }

  // Redirect authenticated users away from auth pages
  if (isAuthPage && isAuthenticated) {
    return NextResponse.redirect(new URL("/chat", nextUrl));
  }

  // Redirect unauthenticated users to login
  if (!isAuthPage && !isAuthenticated && nextUrl.pathname !== "/") {
    return NextResponse.redirect(new URL("/login", nextUrl));
  }

  // Admin route protection — only admin role can access /admin/*
  if (nextUrl.pathname.startsWith("/admin") && req.auth?.user?.role !== "admin") {
    return NextResponse.redirect(new URL("/chat", nextUrl));
  }

  return NextResponse.next();
});

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
