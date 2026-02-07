import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

/**
 * Middleware to check for Authentik authentication headers.
 *
 * When deployed behind the Caddy forward_auth proxy, authenticated requests
 * will have X-Authentik-Username set. Unauthenticated requests are already
 * redirected by Caddy to Authentik's login flow before they reach Next.js.
 *
 * This middleware serves as a defense-in-depth check for protected routes.
 */
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Allow public routes without auth check
  const publicPaths = ['/health', '/api/health', '/_next', '/favicon.ico'];
  if (publicPaths.some(p => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  // Check for Authentik auth header (set by Caddy forward_auth)
  const username = request.headers.get('x-authentik-username');

  if (!username) {
    // In production behind Caddy, this shouldn't happen — Caddy redirects first.
    // But if accessed directly (bypassing proxy), return 401.
    if (pathname.startsWith('/api/')) {
      return NextResponse.json(
        { error: 'Authentication required' },
        { status: 401 }
      );
    }

    // For page routes, redirect to Authentik login
    const loginUrl = new URL('/outpost.goauthentik.io/start', request.url);
    loginUrl.searchParams.set('rd', pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    // Match all routes except static files and Next.js internals
    '/((?!_next/static|_next/image|favicon.ico).*)',
  ],
};
