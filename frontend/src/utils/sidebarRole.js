/**
 * Map the authenticated role onto the names Sidebar switches on.
 *
 * Two vocabularies exist and they do not match: the backend and AuthContext
 * speak `tenant_admin | org_admin | employee`, while Sidebar's switch expects
 * `superadmin | orgadmin | user`. An unmatched value falls through to
 * `default:` and renders an empty menu — which is exactly what happened when
 * the vault pages passed "employee".
 *
 * The vault is used by every role, so these pages cannot hardcode one. They
 * ask who is signed in and translate.
 */

const TO_SIDEBAR = {
  tenant_admin: 'superadmin',
  superadmin: 'superadmin',
  super_admin: 'superadmin',
  org_admin: 'orgadmin',
  orgadmin: 'orgadmin',
  department_admin: 'orgadmin',
  employee: 'user',
  user: 'user',
};

const LABELS = {
  superadmin: 'Tenant Admin',
  orgadmin: 'Org Admin',
  user: 'Employee',
};

const COLOURS = {
  superadmin: { color: '#a855f7', bgColor: 'rgba(168,85,247,0.15)', abbr: 'TA' },
  orgadmin: { color: '#00d4aa', bgColor: 'rgba(0,212,170,0.15)', abbr: 'OA' },
  user: { color: '#f59e0b', bgColor: 'rgba(245,158,11,0.15)', abbr: 'EM' },
};

/**
 * Everything DashboardLayout needs, derived from the signed-in user.
 * Falls back to the employee view — the least privileged menu is the safe
 * default if the role is somehow unrecognised.
 */
export function sidebarPropsFor(user) {
  const key = TO_SIDEBAR[user?.role] || 'user';
  return { role: key, label: LABELS[key], ...COLOURS[key] };
}
