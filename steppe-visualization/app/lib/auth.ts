/**
 * Authentik Authentication Helpers
 *
 * Reads X-Authentik-* headers injected by the Caddy forward_auth proxy.
 * These headers are set by Authentik's outpost after successful authentication.
 */

export interface AuthUser {
  username: string;
  email: string;
  name: string;
  uid: string;
  groups: string[];
  isAuthenticated: boolean;
}

/**
 * Extract authenticated user info from Authentik headers.
 * Headers are injected by Caddy's forward_auth directive via copy_headers.
 */
export function getAuthUser(headers: Headers): AuthUser {
  const username = headers.get('x-authentik-username') || '';
  const email = headers.get('x-authentik-email') || '';
  const name = headers.get('x-authentik-name') || '';
  const uid = headers.get('x-authentik-uid') || '';
  const groupsRaw = headers.get('x-authentik-groups') || '';

  const groups = groupsRaw
    ? groupsRaw.split('|').filter(Boolean)
    : [];

  return {
    username,
    email,
    name,
    uid,
    groups,
    isAuthenticated: !!username,
  };
}
