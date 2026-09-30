
// src/services/api.js
const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'https://api-work.gridsphere.in';

// Helper to get auth token
const getToken = () => localStorage.getItem('access_token');

// Helper to get API key (for tenant)
const getApiKey = () => localStorage.getItem('api_key');

// Helper to get auth type. Kept for callers that still read it; routing no
// longer depends on it — see pickAuthHeaders().
const getAuthType = () => localStorage.getItem('auth_type');

// Everything under this prefix authenticates with the tenant API key.
// Every other route uses a JWT.
const TENANT_PREFIX = '/api/tenant/';

// The organisation a Super Admin is currently administering.
//
// Kept in localStorage rather than in the URL: it is a property of the session,
// not of the page, and every Tenant Admin screen would otherwise need to carry
// it through every link and redirect. It is a convenience for the client only
// — the server re-checks on every request that the caller is actually a Super
// Admin before honouring it.
const ACTING_TENANT_KEY = 'acting_tenant_id';

export const getActingTenantId = () => localStorage.getItem(ACTING_TENANT_KEY);

export const setActingTenant = (tenant) => {
  if (tenant?.id == null) localStorage.removeItem(ACTING_TENANT_KEY);
  else {
    localStorage.setItem(ACTING_TENANT_KEY, String(tenant.id));
    localStorage.setItem('acting_tenant_name', tenant.name || '');
  }
};

export const getActingTenantName = () => localStorage.getItem('acting_tenant_name');

export const clearActingTenant = () => {
  localStorage.removeItem(ACTING_TENANT_KEY);
  localStorage.removeItem('acting_tenant_name');
};

/**
 * Choose the credential from the ENDPOINT, not from a global `auth_type` flag.
 *
 * The old behaviour read one `auth_type` value and applied it to every
 * request, which broke as soon as two roles were used in the same browser:
 * signing in as Org Admin set auth_type='bearer', so an open Tenant Admin tab
 * started sending `Authorization: Bearer <org-admin-jwt>` to /api/tenant/*.
 * Those routes require an `X-API-Key` header, and FastAPI reports a missing
 * required header as 422 Unprocessable Entity — which reads like a bad request
 * body rather than "you sent the wrong credential".
 *
 * Deciding per endpoint makes the choice unambiguous no matter what was signed
 * into last, and lets both sessions coexist.
 */
function pickAuthHeaders(endpoint) {
  const headers = {};
  const token = getToken();

  if (endpoint.startsWith(TENANT_PREFIX)) {
    const apiKey = getApiKey();
    // Prefer the API key; fall back to the JWT. The backend accepts either on
    // these routes, so a tenant admin signed in with email and password works
    // without having the key to hand. Sending neither used to surface as a
    // 422; now it is a 401 with a sentence explaining itself.
    if (apiKey) headers['X-API-Key'] = apiKey;
    else if (token) headers['Authorization'] = `Bearer ${token}`;

    // Which organisation a Super Admin is acting within. They have no tenant of
    // their own, so every route here needs to be told. The backend honours this
    // only for super_admin and refuses it from anyone else, so sending it
    // unconditionally is safe — a tenant admin with a stale value gets a clear
    // 403 rather than silently acting on the wrong organisation.
    const acting = getActingTenantId();
    if (acting) headers['X-Acting-Tenant-Id'] = acting;
    return headers;
  }

  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
}

// Generic API request function
async function apiRequest(endpoint, options = {}) {
  const headers = pickAuthHeaders(endpoint);

  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }
  
  const finalHeaders = { ...headers, ...options.headers };
  
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers: finalHeaders,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const err = new Error(describeApiError(error, response.status));
    // Carried through so callers can react to specific failures — the reveal
    // flow needs to distinguish "re-authenticate" from a general 401.
    err.status = response.status;
    err.stepUpRequired = response.headers.get('X-Step-Up-Required');
    // A Super Admin with no organisation selected. Not a failure to show as an
    // error — the caller turns it into the organisation chooser.
    err.needsTenantChoice = (
      response.status === 409 && endpoint.startsWith(TENANT_PREFIX)
    );
    throw err;
  }

  // 204 and other empty bodies: calling .json() on them throws, which would
  // turn a successful DELETE into an error.
  if (response.status === 204 || response.headers.get('content-length') === '0') {
    return null;
  }
  return response.json().catch(() => null);
}

// FastAPI reports validation failures as a LIST of objects under `detail`.
// Passing that straight to new Error() stringifies it to "[object Object]",
// which hid the real cause of every 422. Turn it into something readable.
function describeApiError(error, status) {
  const detail = error?.detail;

  if (typeof detail === 'string' && detail) return detail;

  if (Array.isArray(detail)) {
    const parts = detail.map((d) => {
      // loc is like ["body", "due_date"] — the first element is the source.
      const field = Array.isArray(d?.loc) ? d.loc.slice(1).join('.') : '';
      const msg = d?.msg || 'invalid value';
      return field ? `${field}: ${msg}` : msg;
    });
    return parts.join('; ') || `API Error: ${status}`;
  }

  if (detail && typeof detail === 'object') {
    return detail.message || JSON.stringify(detail);
  }

  return error?.message || `API Error: ${status}`;
}

// ==================== EMPLOYEE APIs ====================
export const employeeApi = {
  getDashboard: () => apiRequest('/api/employee/dashboard'),
  getTodayAttendance: () => apiRequest('/api/employee/attendance/today'),
  getAttendanceHistory: () => apiRequest('/api/employee/attendance'),
  getMonthlyStats: (month, year) => {
    const params = new URLSearchParams();
    if (month) params.append('month', month);
    if (year) params.append('year', year);
    return apiRequest(`/api/employee/attendance/stats/monthly?${params.toString()}`);
  },
  getHoursSummary: (month, year) => {
    const params = new URLSearchParams();
    if (month) params.append('month', month);
    if (year) params.append('year', year);
    return apiRequest(`/api/employee/attendance/hours/summary?${params.toString()}`);
  },
  getCalendar: (month, year) => {
    const params = new URLSearchParams();
    if (month) params.append('month', month);
    if (year) params.append('year', year);
    return apiRequest(`/api/employee/attendance/calendar?${params.toString()}`);
  },
  getProfile: () => apiRequest('/api/employee/profile'),
  updateProfile: (data) => apiRequest('/api/employee/profile', { method: 'PUT', body: JSON.stringify(data) }),
  changePassword: (data) => apiRequest('/api/employee/profile/change-password', { method: 'PUT', body: JSON.stringify(data) }),
  getLeaves: () => apiRequest('/api/employee/leaves'),
  getLeaveBalance: () => apiRequest('/api/employee/leaves/balance'),
  getLeaveStats: () => apiRequest('/api/employee/leaves/stats'),
  applyLeave: (data) => apiRequest('/api/employee/leaves', { method: 'POST', body: JSON.stringify(data) }),
  cancelLeave: (id) => apiRequest(`/api/employee/leaves/${id}/cancel`, { method: 'PATCH' }),
  getHolidays: () => apiRequest('/api/employee/holidays'),
  getUpcomingHoliday: () => apiRequest('/api/employee/holidays/upcoming'),
  getNotifications: (limit = 50, unreadOnly = false) => 
    apiRequest(`/api/employee/notifications?limit=${limit}&unread_only=${unreadOnly}`),
  getUnreadCount: () => apiRequest('/api/employee/notifications/unread-count'),
  markNotificationRead: (id) => apiRequest(`/api/employee/notifications/${id}/read`, { method: 'PATCH' }),
  markAllRead: () => apiRequest('/api/employee/notifications/read-all', { method: 'PATCH' }),
};

// ==================== ORGANIZATION ADMIN APIs ====================
export const orgApi = {
  getDashboard: () => apiRequest('/api/org/dashboard'),
  changePassword: (data) => apiRequest('/api/auth/change-password', { 
    method: 'POST', 
    body: JSON.stringify(data) 
  }),
  getEmployees: () => apiRequest('/api/org/employees'),
  getAvailableSlots: () => apiRequest('/api/org/employees/available-finger-slots'),
  createEmployee: (data) => apiRequest('/api/org/employees', { method: 'POST', body: JSON.stringify(data) }),
  updateEmployee: (id, data) => apiRequest(`/api/org/employees/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteEmployee: (id) => apiRequest(`/api/org/employees/${id}`, { method: 'DELETE' }),
  assignFingerprint: (id, data) => apiRequest(`/api/org/employees/${id}/assign-fingerprint`, { method: 'PATCH', body: JSON.stringify(data) }),
  getTodayAttendance: () => apiRequest('/api/org/attendance/today'),
  getAttendanceByDate: (date) => apiRequest(`/api/org/attendance/date/${date}`),
  getLeaveRequests: () => apiRequest('/api/org/leaves'),
  approveLeave: (id) => apiRequest(`/api/org/leaves/${id}/approve`, { method: 'PATCH' }),
  rejectLeave: (id, reason) => apiRequest(`/api/org/leaves/${id}/reject`, { method: 'PATCH', body: JSON.stringify({ reason }) }),
  getHolidays: () => apiRequest('/api/org/holidays'),
  getUpcomingHolidays: (limit = 5) => apiRequest(`/api/org/holidays/upcoming?limit=${limit}`),
  // Device management
  getDevices: () => apiRequest('/api/org/devices'),
  getDeviceStatus: () => apiRequest('/api/org/devices/status'),
  createDevice: (data) => apiRequest('/api/org/devices', { method: 'POST', body: JSON.stringify(data) }),
  fireCommand: (data) => apiRequest('/api/org/devices/fire-command', { method: 'POST', body: JSON.stringify(data) }),
  getActivityLog: () => apiRequest('/api/org/activity'),
};

// ==================== SHARED BY EVERY SIGNED-IN ROLE ====================
//
// Office hours are one tenant-wide fact that the attendance screens for all
// three roles need. They used to be read from /api/tenant/settings, which
// answers anyone who is not a Tenant Admin with a 403 — so the Org Admin and
// employee pages caught the error and fell back to their own hardcoded values.
// The numbers looked authoritative and were not coming from the database.
export const commonApi = {
  getSettings: () => apiRequest('/api/settings'),
};

// Removed as dead: getActivityLog, getRecentAttendance, getAttendanceStats,
// getPendingLeaves, findEmployeeByFingerprint, getDepartmentSummary,
// updateDepartmentStatus (tenant) and exportData, getByDate, getLeaveDetail,
// getAttendanceSummary (employee). No page called any of them and none had a
// backend route — see backend/tests/test_api_contract.py.

// ==================== TENANT ADMIN APIs ====================
export const tenantApi = {
  getDashboard: () => apiRequest('/api/tenant/dashboard'),
  changeApiKey: (apiKey) => apiRequest('/api/tenant/change-api-key', { 
    method: 'POST', 
    body: JSON.stringify({ api_key: apiKey }) 
  }),
  getAttendanceByDate: (date, deptId) => {
    const params = deptId ? `?dept_id=${deptId}` : '';
    return apiRequest(`/api/tenant/attendance/date/${date}${params}`);
  },
  getAttendanceReport: (startDate, endDate, deptId) => {
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    if (deptId) params.append('dept_id', deptId);
    return apiRequest(`/api/tenant/reports/attendance?${params.toString()}`);
  },
  getDepartments: () => apiRequest('/api/tenant/departments'),
  createDepartment: (data) => apiRequest('/api/tenant/departments', { method: 'POST', body: JSON.stringify(data) }),
  updateDepartment: (id, data) => apiRequest(`/api/tenant/departments/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteDepartment: (id) => apiRequest(`/api/tenant/departments/${id}`, { method: 'DELETE' }),
  getHolidays: (year) => {
    const params = year ? `?year=${year}` : '';
    return apiRequest(`/api/tenant/holidays${params}`);
  },
  createHoliday: (data) => apiRequest('/api/tenant/holidays', { method: 'POST', body: JSON.stringify(data) }),
  getTenantProfile: () => apiRequest('/api/tenant/profile'),
  updateHoliday: (id, data) => apiRequest(`/api/tenant/holidays/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteHoliday: (id) => apiRequest(`/api/tenant/holidays/${id}`, { method: 'DELETE' }),
  getUpcomingHolidays: (limit = 5) => apiRequest(`/api/tenant/holidays/upcoming?limit=${limit}`),
  getDevices: () => apiRequest('/api/tenant/devices'),
  getDeviceStatus: () => apiRequest('/api/tenant/devices/status'),
  getDeviceDetails: (deviceId) => apiRequest(`/api/tenant/devices/${deviceId}`),
  createDevice: (data) => apiRequest('/api/tenant/devices', { method: 'POST', body: JSON.stringify(data) }),
  updateDevice: (deviceId, data) => apiRequest(`/api/tenant/devices/${deviceId}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteDevice: (deviceId) => apiRequest(`/api/tenant/devices/${deviceId}`, { method: 'DELETE' }),
  fireCommand: (data) => apiRequest('/api/tenant/devices/fire-command', { method: 'POST', body: JSON.stringify(data) }),
  getOrgAdmins: () => apiRequest('/api/tenant/org-admins'),
  createOrgAdmin: (data) => apiRequest('/api/tenant/org-admins', { method: 'POST', body: JSON.stringify(data) }),
  updateOrgAdmin: (id, data) => apiRequest(`/api/tenant/org-admins/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteOrgAdmin: (id) => apiRequest(`/api/tenant/org-admins/${id}`, { method: 'DELETE' }),
  getLeaveStats: () => apiRequest('/api/tenant/leaves/stats'),
  getLeaveRequests: (status, deptId) => {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (deptId) params.append('dept_id', deptId);
    return apiRequest(`/api/tenant/leaves?${params.toString()}`);
  },
  approveLeave: (id) => apiRequest(`/api/tenant/leaves/${id}/approve`, { method: 'PATCH' }),
  rejectLeave: (id, reason) => {
    const body = reason ? JSON.stringify({ reason }) : '{}';
    return apiRequest(`/api/tenant/leaves/${id}/reject`, { method: 'PATCH', body });
  },
  getAllEmployees: (deptId) => {
    const params = deptId ? `?dept_id=${deptId}` : '';
    return apiRequest(`/api/tenant/employees${params}`);
  },
  getEmployeeDetail: (id) => apiRequest(`/api/tenant/employees/${id}`),
  getEmployeeAttendance: (id, month, year) => {
    const params = new URLSearchParams();
    if (month) params.append('month', month);
    if (year) params.append('year', year);
    return apiRequest(`/api/tenant/employees/${id}/attendance?${params.toString()}`);
  },
  getSettings: () => apiRequest('/api/tenant/settings'),
  updateSettings: (data) => apiRequest('/api/tenant/settings', { method: 'PUT', body: JSON.stringify(data) }),
  getTenantProfile: () => apiRequest('/api/tenant/profile'),
};

// ==================== SUPER ADMIN APIs ====================
// Platform level: these act on organisations from outside them, so they never
// carry X-Acting-Tenant-Id (only /api/tenant/* does — see pickAuthHeaders).
export const superAdminApi = {
  getOverview: () => apiRequest('/api/super/overview'),
  getTenants: () => apiRequest('/api/super/tenants'),
  /** { name, admin_name, admin_email, admin_password, department? } */
  createTenant: (data) => apiRequest('/api/super/tenants', { method: 'POST', body: JSON.stringify(data) }),
  getTenantDetails: (id) => apiRequest(`/api/super/tenants/${id}`),
  renameTenant: (id, name) => apiRequest(`/api/super/tenants/${id}`, { method: 'PATCH', body: JSON.stringify({ name }) }),
  resetTenantApiKey: (id) => apiRequest(`/api/super/tenants/${id}/reset-api-key`, { method: 'PATCH' }),
  deleteTenant: (id) => apiRequest(`/api/super/tenants/${id}`, { method: 'DELETE' }),
};

// ==================== AUTH APIs ====================
export const authApi = {
  login: (username, password) => {
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);
    
    return fetch(`${API_BASE_URL}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: formData,
    }).then(async (response) => {
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || 'Login failed');
      }
      const data = await response.json();
      // The tenant API key is deliberately left alone. It lives under a
      // different key and is only used for /api/tenant/*, so keeping it lets a
      // Tenant Admin tab stay signed in while you use another role elsewhere.
      // Removing it here is what used to break that tab with a 422.
      localStorage.setItem('auth_type', 'bearer');
      localStorage.setItem('access_token', data.access_token);
      if (data.refresh_token) localStorage.setItem('refresh_token', data.refresh_token);
      return data;
    });
  },
  
  tenantLogin: (apiKey) => {
    return fetch(`${API_BASE_URL}/api/auth/tenant-login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: apiKey }),
    }).then(async (response) => {
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || 'Invalid API Key');
      }
      const data = await response.json();
      // Likewise: the JWT is left in place. Signing in as Tenant Admin used to
      // delete it, silently logging out an Org Admin or Employee tab.
      localStorage.setItem('api_key', apiKey);
      localStorage.setItem('auth_type', 'api_key');
      return data;
    });
  },
  
  refreshToken: (refreshToken) => apiRequest('/api/auth/refresh', { 
    method: 'POST', 
    body: JSON.stringify({ refresh_token: refreshToken }) 
  }),
  
  logout: () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('api_key');
    localStorage.removeItem('auth_type');
    localStorage.removeItem('user');
  },
  
  changePassword: (data) => apiRequest('/api/auth/change-password', { method: 'POST', body: JSON.stringify(data) }),
  setPassword: (data) => apiRequest('/api/auth/set-password', { method: 'POST', body: JSON.stringify(data) }),
  createSuperAdmin: (data) => apiRequest('/api/auth/setup/super-admin', { method: 'POST', body: JSON.stringify(data) }),
};

// ─── Credential vault ────────────────────────────────────────────────────────
// Reveal is the only call taking a step-up token. It goes in a header rather
// than the body because it authorises the request, not the payload — and a
// header stays out of any JSON request logging.

export const vaultApi = {
  // What this caller may do, so the UI stops offering actions that 403.
  myPermissions: () => apiRequest('/api/vault/me/permissions'),

  // MFA
  mfaStatus: () => apiRequest('/api/vault/mfa/status'),
  // Returns { secret, provisioning_uri }. The URI is the otpauth:// string
  // that becomes a QR code — use it, do not make people type the raw secret.
  beginEnrolment: (label) =>
    apiRequest('/api/vault/mfa/enrol', {
      method: 'POST',
      body: JSON.stringify({ label: label || null }),
    }),
  confirmEnrolment: (code) =>
    apiRequest('/api/vault/mfa/enrol/confirm', {
      method: 'POST',
      body: JSON.stringify({ code }),
    }),
  stepUp: (code, purpose = 'credential.reveal') =>
    apiRequest('/api/vault/mfa/step-up', {
      method: 'POST',
      body: JSON.stringify({ code, purpose }),
    }),

  // Vaults and racks
  vaults: () => apiRequest('/api/vault/vaults'),
  createRack: (vaultId, data) =>
    apiRequest(`/api/vault/racks?vault_id=${vaultId}`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Credentials
  list: ({ rackId, search, limit } = {}) => {
    const q = new URLSearchParams();
    if (rackId) q.set('rack_id', rackId);
    if (search) q.set('search', search);
    if (limit) q.set('limit', limit);
    const qs = q.toString();
    return apiRequest(`/api/vault/credentials${qs ? `?${qs}` : ''}`);
  },
  create: (data) =>
    apiRequest('/api/vault/credentials', { method: 'POST', body: JSON.stringify(data) }),
  update: (id, data) =>
    apiRequest(`/api/vault/credentials/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  rotate: (id, data) =>
    apiRequest(`/api/vault/credentials/${id}/rotate`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  remove: (id) => apiRequest(`/api/vault/credentials/${id}`, { method: 'DELETE' }),

  reveal: (id, stepUpToken) =>
    apiRequest(`/api/vault/credentials/${id}/reveal`, {
      method: 'POST',
      headers: { 'X-Step-Up-Token': stepUpToken },
    }),

  // Copying cannot be prevented — anyone who can see a secret can retype it.
  // This records that it happened, which is the honest half of the promise.
  recordCopy: (id) =>
    apiRequest(`/api/vault/credentials/${id}/copied`, { method: 'POST' }),

  // Sharing
  sharedWithMe: () => apiRequest('/api/vault/shared-with-me'),
  shareTree: (credentialId) =>
    apiRequest(`/api/vault/credentials/${credentialId}/shares`),
  share: (credentialId, data) =>
    apiRequest(`/api/vault/credentials/${credentialId}/shares`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  revokeShare: (shareId, reason) =>
    apiRequest(`/api/vault/shares/${shareId}`, {
      method: 'DELETE',
      body: JSON.stringify({ reason: reason || null }),
    }),

  // Security scoring and rotation policy
  security: (credentialId) =>
    apiRequest(`/api/vault/credentials/${credentialId}/security`),
  securityOverview: (severity) =>
    apiRequest(`/api/vault/security/overview${severity ? `?severity=${severity}` : ''}`),
  thresholds: () => apiRequest('/api/vault/security/thresholds'),
  createPolicy: (data) =>
    apiRequest('/api/vault/security/rotation-policies', {
      method: 'POST', body: JSON.stringify(data),
    }),

  // Dependencies
  systems: () => apiRequest('/api/vault/systems'),
  dependencies: (credentialId) =>
    apiRequest(`/api/vault/credentials/${credentialId}/dependencies`),
  addDependency: (credentialId, data) =>
    apiRequest(`/api/vault/credentials/${credentialId}/dependencies`, {
      method: 'POST', body: JSON.stringify(data),
    }),
  removeDependency: (dependencyId) =>
    apiRequest(`/api/vault/dependencies/${dependencyId}`, { method: 'DELETE' }),
  dependencyGraph: () => apiRequest('/api/vault/dependency-graph'),

  // What breaks if this is rotated or revoked. Called BEFORE the action.
  impact: (credentialId, action = 'rotate') =>
    apiRequest(`/api/vault/credentials/${credentialId}/impact?action=${action}`),

  // Activity and audit
  activity: (credentialId) =>
    apiRequest(`/api/vault/credentials/${credentialId}/activity`),
  auditLog: (filters = {}) => {
    const q = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') q.set(k, v);
    });
    const qs = q.toString();
    return apiRequest(`/api/vault/audit${qs ? `?${qs}` : ''}`);
  },
  auditActions: () => apiRequest('/api/vault/audit/actions'),
  auditSummary: (days = 7) => apiRequest(`/api/vault/audit/summary?days=${days}`),
  auditIntegrity: () => apiRequest('/api/vault/audit/integrity'),

  /**
   * Download the audit CSV.
   *
   * Fetched rather than linked: a plain <a href> carries no Authorization
   * header, so the request would arrive unauthenticated and 401. This pulls
   * the file with credentials attached and hands the browser a blob.
   */
  downloadAudit: async (filters = {}) => {
    const q = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') q.set(k, v);
    });

    const token = localStorage.getItem('access_token');
    const response = await fetch(
      `${API_BASE_URL}/api/vault/audit/export.csv?${q.toString()}`,
      { headers: token ? { Authorization: `Bearer ${token}` } : {} },
    );
    if (!response.ok) throw new Error(`Export failed (${response.status})`);

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `audit-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    // Released on the next tick — revoking immediately can cancel the download
    // in some browsers before it has started reading.
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};

// publicApi.getTenantSettings was removed. It called
// /api/tenant/settings/public, a route that was never written, and swallowed
// the 404 by returning hardcoded office hours — so the employee dashboard
// displayed made-up values and reported no error. Use commonApi.getSettings(),
// which is authenticated, reads the tenant from the token, and fails loudly.




// ==================== TASK MANAGER APIs ====================

// Turns a filter object into a query string, dropping empty values so the
// backend sees an absent filter rather than an empty one.
function taskQuery(filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      params.append(key, value);
    }
  });
  const qs = params.toString();
  return qs ? `?${qs}` : '';
}

// Tenant admin — full control, plus GitHub repo configuration
export const tenantTaskApi = {
  list: (filters) => apiRequest(`/api/tenant/tasks${taskQuery(filters)}`),
  stats: () => apiRequest('/api/tenant/tasks/stats'),
  assignableUsers: (deptId) =>
    apiRequest(`/api/tenant/tasks/assignable-users${taskQuery({ dept_id: deptId })}`),
  pushableRepos: () => apiRequest('/api/tenant/github/repos'),
  create: (data) =>
    apiRequest('/api/tenant/tasks', { method: 'POST', body: JSON.stringify(data) }),
  update: (id, data) =>
    apiRequest(`/api/tenant/tasks/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  remove: (id) => apiRequest(`/api/tenant/tasks/${id}`, { method: 'DELETE' }),
  push: (id, repoId) =>
    apiRequest(`/api/tenant/tasks/${id}/push`, {
      method: 'POST',
      body: JSON.stringify({ github_repo_id: repoId || null }),
    }),
  comments: (id) => apiRequest(`/api/tenant/tasks/${id}/comments`),
  addComment: (id, body) =>
    apiRequest(`/api/tenant/tasks/${id}/comments`, {
      method: 'POST',
      body: JSON.stringify({ body }),
    }),

  // GitHub repo configuration
  listRepos: () => apiRequest('/api/tenant/github/repos'),
  addRepo: (data) =>
    apiRequest('/api/tenant/github/repos', { method: 'POST', body: JSON.stringify(data) }),
  updateRepo: (id, data) =>
    apiRequest(`/api/tenant/github/repos/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  syncRepo: (id) => apiRequest(`/api/tenant/github/repos/${id}/sync`, { method: 'POST' }),
  syncAll: () => apiRequest('/api/tenant/github/sync', { method: 'POST' }),
  writeAccess: (id) => apiRequest(`/api/tenant/github/repos/${id}/write-access`),
  // Who GitHub will accept as an assignee on this repo (push access only)
  repoAssignees: (id) => apiRequest(`/api/tenant/github/repos/${id}/assignees`),

  // GitHub login mapping, needed to mirror assignment onto issues
  listUserMapping: () => apiRequest('/api/tenant/github/user-mapping'),
  setUserMapping: (userId, githubUsername) =>
    apiRequest(`/api/tenant/github/user-mapping/${userId}`, {
      method: 'PUT',
      body: JSON.stringify({ github_username: githubUsername }),
    }),
  removeRepo: (id, deleteTasks = false) =>
    apiRequest(`/api/tenant/github/repos/${id}?delete_tasks=${deleteTasks}`, {
      method: 'DELETE',
    }),
};

// Org admin — manages tasks for their organisation
export const orgTaskApi = {
  list: (filters) => apiRequest(`/api/org/tasks${taskQuery(filters)}`),
  stats: () => apiRequest('/api/org/tasks/stats'),
  assignableUsers: (deptId) =>
    apiRequest(`/api/org/tasks/assignable-users${taskQuery({ dept_id: deptId })}`),
  pushableRepos: () => apiRequest('/api/org/tasks/github-repos'),
  syncAll: () => apiRequest('/api/org/tasks/github-sync', { method: 'POST' }),
  create: (data) =>
    apiRequest('/api/org/tasks', { method: 'POST', body: JSON.stringify(data) }),
  update: (id, data) =>
    apiRequest(`/api/org/tasks/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  remove: (id) => apiRequest(`/api/org/tasks/${id}`, { method: 'DELETE' }),
  push: (id, repoId) =>
    apiRequest(`/api/org/tasks/${id}/push`, {
      method: 'POST',
      body: JSON.stringify({ github_repo_id: repoId || null }),
    }),
  comments: (id) => apiRequest(`/api/org/tasks/${id}/comments`),
  addComment: (id, body) =>
    apiRequest(`/api/org/tasks/${id}/comments`, {
      method: 'POST',
      body: JSON.stringify({ body }),
    }),
};

// Employee — own tasks, status changes only
export const employeeTaskApi = {
  list: (filters) => apiRequest(`/api/employee/tasks${taskQuery(filters)}`),
  stats: () => apiRequest('/api/employee/tasks/stats'),
  setStatus: (id, status) =>
    apiRequest(`/api/employee/tasks/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),
  comments: (id) => apiRequest(`/api/employee/tasks/${id}/comments`),
  addComment: (id, body) =>
    apiRequest(`/api/employee/tasks/${id}/comments`, {
      method: 'POST',
      body: JSON.stringify({ body }),
    }),
};

// Backward compatibility
export const attendanceAPI = employeeApi;
export const profileAPI = employeeApi;
export const dashboardAPI = employeeApi;
export const leavesAPI = employeeApi;
export const holidaysAPI = employeeApi;
export const notificationsAPI = employeeApi;

export default {
  employee: employeeApi,
  org: orgApi,
  tenant: tenantApi,
  superAdmin: superAdminApi,
  auth: authApi,
  common: commonApi,
  tenantTasks: tenantTaskApi,
  orgTasks: orgTaskApi,
  employeeTasks: employeeTaskApi,
};



