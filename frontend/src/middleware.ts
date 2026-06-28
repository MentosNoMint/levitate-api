import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const { pathname, searchParams } = request.nextUrl;
  let token = request.cookies.get("auth_token")?.value;

  const tokenFromUrl = searchParams.get("auth_token");
  if (tokenFromUrl) {
    const targetPath = pathname === "/" ? "/overview" : pathname;
    const response = NextResponse.redirect(new URL(targetPath, request.url));
    response.cookies.set("auth_token", tokenFromUrl, {
      path: "/",
      maxAge: 2592000,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
    });
    return response;
  }

  if (!token && pathname !== "/login") {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  if (token && pathname === "/login") {
    return NextResponse.redirect(new URL("/overview", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|icon.svg).*)"],
};
