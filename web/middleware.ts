import { NextRequest, NextResponse } from "next/server";

/**
 * Dashboard auth.
 *
 * The dashboard surfaces PII (chat events, ticket emails, document filenames and
 * summaries), so two-layer protection applies:
 *
 *  1. Network gate — `web` is bound to 127.0.0.1 in docker-compose, so by default the
 *     dashboard is unreachable from the LAN.
 *  2. Opt-in token — when `DASHBOARD_TOKEN` is set, requests must present it:
 *     - API: `x-dashboard-token: <token>` header, OR the `aura_dash` cookie.
 *     - Page: the `aura_dash` cookie. Visit `/dashboard?t=<token>` once to mint it;
 *       middleware sets the cookie and redirects to a clean URL.
 *
 * If `DASHBOARD_TOKEN` is unset, only the network gate applies (single-dev default,
 * same posture as the Dozzle container).
 */
const TOKEN = process.env.DASHBOARD_TOKEN;
const COOKIE = "aura_dash";

function authorized(req: NextRequest): boolean {
  if (!TOKEN) return true;
  if (req.headers.get("x-dashboard-token") === TOKEN) return true;
  if (req.cookies.get(COOKIE)?.value === TOKEN) return true;
  return false;
}

export function middleware(req: NextRequest) {
  // One-time cookie mint from ?t=TOKEN on the page.
  if (TOKEN && req.nextUrl.pathname === "/dashboard") {
    const t = req.nextUrl.searchParams.get("t");
    if (t === TOKEN) {
      const url = req.nextUrl.clone();
      url.searchParams.delete("t");
      const res = NextResponse.redirect(url);
      res.cookies.set(COOKIE, TOKEN, {
        httpOnly: true,
        sameSite: "strict",
        path: "/",
      });
      return res;
    }
  }

  if (authorized(req)) return NextResponse.next();

  if (req.nextUrl.pathname.startsWith("/api/")) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  return new NextResponse(
    "Unauthorized. Set DASHBOARD_TOKEN and visit /dashboard?t=<token> once.",
    { status: 401 },
  );
}

export const config = {
  matcher: ["/api/dashboard/:path*", "/dashboard"],
};
