// src/utils/roles.js
//
// One place that decides what a role is called and where it lands.
//
// This mapping previously existed three times — in AuthContext's token
// decoder, in ProtectedRoute's redirect, and implicitly in the per-role login
// pages — and they did not agree. The login pages assigned a role from the URL
// the person had chosen, while AuthContext assigned one from the token. Pick
// "Tenant Admin" on the old gateway, sign in as an employee, and until the
// next reload the app believed you were a tenant admin. The API still refused
// every request, so nothing leaked, but you were shown a dashboard shell you
// had no access to and a screen full of errors.

/** Backend roles that map onto each of the three the frontend routes on. */
const ALIASES = {
  tenant_admin: 'tenant_admin',
  superadmin: 'tenant_admin',
  super_admin: 'tenant_admin',
  org_admin: 'org_admin',
  department_admin: 'org_admin',
  employee: 'employee',
  user: 'employee',
};

export const ROLE_LABEL = {
  tenant_admin: 'Tenant Admin',
  org_admin: 'Org Admin',
  employee: 'Employee',
};

const HOME = {
  tenant_admin: '/super/dashboard',
  org_admin: '/org/dashboard',
  employee: '/emp/dashboard',
};

/**
 * Backend role to the one the frontend routes on.
 *
 * Returns null for anything unrecognised rather than guessing. A role that
 * falls through to a default is a role that silently gains whatever that
 * default can reach; better to treat it as "no access" and have it show up.
 */
export function normaliseRole(raw) {
  if (!raw) return null;
  return ALIASES[String(raw).toLowerCase()] || null;
}

/** Where this role belongs after signing in. */
export function homePathFor(role) {
  return HOME[normaliseRole(role)] || '/';
}

/**
 * Is this the platform operator?
 *
 * A Super Admin is routed as a tenant_admin — they use the same screens once
 * they have picked an organisation — so `user.role` cannot tell them apart.
 * `originalRole` is the unnormalised value from the token and can.
 */
export function isSuperAdmin(user) {
  return user?.originalRole === 'super_admin';
}

/** The platform home: every organisation, before choosing one to work in. */
export const PLATFORM_HOME = '/platform/organisations';

/**
 * Where this person belongs, when the role alone is not enough.
 *
 * Prefer this over homePathFor wherever a user object is to hand. A Super
 * Admin sent to the tenant dashboard has no organisation selected yet, so the
 * dashboard bounces them to the chooser — two redirects to arrive somewhere
 * less useful than the platform screen, which is where they start.
 */
export function homePathForUser(user) {
  return isSuperAdmin(user) ? PLATFORM_HOME : homePathFor(user?.role);
}

/**
 * Decode a JWT payload without verifying it.
 *
 * Verification is the server's job and only the server can do it — it holds
 * the key. This is read purely to decide which screens to draw. Every request
 * the resulting UI makes is authorised server-side against the same token, so
 * a forged payload buys a wrong-looking menu and a page of 403s, not access.
 */
export function decodeToken(token) {
  try {
    const [, payload] = token.split('.');
    // base64url -> base64, and atob gives Latin-1, so route it through
    // decodeURIComponent to survive non-ASCII names.
    const b64 = payload.replace(/-/g, '+').replace(/_/g, '/');
    const json = decodeURIComponent(
      atob(b64).split('').map((c) => `%${c.charCodeAt(0).toString(16).padStart(2, '0')}`).join(''),
    );
    return JSON.parse(json);
  } catch {
    return null;
  }
}

/** The user object the app runs on, built from the token and nothing else. */
export function userFromToken(token) {
  const payload = decodeToken(token);
  if (!payload) return null;

  const role = normaliseRole(payload.role);
  if (!role) return null;

  return {
    id: payload.user_id ?? payload.sub ?? payload.id ?? null,
    role,
    originalRole: payload.role,
    tenant_id: payload.tenant_id ?? null,
    dept_id: payload.dept_id ?? null,
    name: payload.name || null,
    email: payload.email || null,
  };
}
