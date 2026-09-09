
// src/services/api.js
const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'https://api.attendance.gridsphere.in';

// Helper to get auth token
const getToken = () => localStorage.getItem('access_token');

// Helper to get API key (for tenant)
const getApiKey = () => localStorage.getItem('api_key');

// Helper to get auth type
const getAuthType = () => localStorage.getItem('auth_type');

// Generic API request function
async function apiRequest(endpoint, options = {}) {
  const token = getToken();
  const apiKey = getApiKey();
  const authType = getAuthType();
  
  const headers = {};
  
  if (authType === 'api_key' && apiKey) {
    headers['X-API-Key'] = apiKey;
  } else if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  
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
    throw new Error(describeApiError(error, response.status));
  }

  return response.json();
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
  getAttendanceStats: () => apiRequest('/api/employee/attendance/stats'),
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
  getByDate: (date) => apiRequest(`/api/employee/attendance/${date}`),
  exportData: () => apiRequest('/api/employee/attendance/export'),
  getProfile: () => apiRequest('/api/employee/profile'),
  updateProfile: (data) => apiRequest('/api/employee/profile', { method: 'PUT', body: JSON.stringify(data) }),
  changePassword: (data) => apiRequest('/api/employee/profile/change-password', { method: 'PUT', body: JSON.stringify(data) }),
  getAttendanceSummary: () => apiRequest('/api/employee/profile/attendance-summary'),
  getLeaves: () => apiRequest('/api/employee/leaves'),
  getLeaveBalance: () => apiRequest('/api/employee/leaves/balance'),
  getLeaveStats: () => apiRequest('/api/employee/leaves/stats'),
  applyLeave: (data) => apiRequest('/api/employee/leaves', { method: 'POST', body: JSON.stringify(data) }),
  getLeaveDetail: (id) => apiRequest(`/api/employee/leaves/${id}`),
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
  getAttendance: (date) => apiRequest(`/api/org/attendance?date=${date}`),
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
  getSettings: () => apiRequest('/api/org/settings'),
  updateSettings: (data) => apiRequest('/api/org/settings', { method: 'PUT', body: JSON.stringify(data) }),
};

// ==================== TENANT ADMIN APIs ====================
export const tenantApi = {
  getDashboard: () => apiRequest('/api/tenant/dashboard'),
  changeApiKey: (apiKey) => apiRequest('/api/tenant/change-api-key', { 
    method: 'POST', 
    body: JSON.stringify({ api_key: apiKey }) 
  }),
  getRecentAttendance: () => apiRequest('/api/tenant/attendance/recent'),
  getAttendanceStats: () => apiRequest('/api/tenant/attendance/stats'),
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
  getDepartmentSummary: (month, year) => {
    const params = new URLSearchParams();
    if (month) params.append('month', month);
    if (year) params.append('year', year);
    return apiRequest(`/api/tenant/reports/department-summary?${params.toString()}`);
  },
  getDepartments: () => apiRequest('/api/tenant/departments'),
  createDepartment: (data) => apiRequest('/api/tenant/departments', { method: 'POST', body: JSON.stringify(data) }),
  updateDepartment: (id, data) => apiRequest(`/api/tenant/departments/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  updateDepartmentStatus: (id, data) => apiRequest(`/api/tenant/departments/${id}/status`, { method: 'PATCH', body: JSON.stringify(data) }),
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
  getPendingLeaves: () => apiRequest('/api/tenant/leaves/pending'),
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
  findEmployeeByFingerprint: (fingerId) => apiRequest(`/api/tenant/employees/fingerprint/${fingerId}`),
  getSettings: () => apiRequest('/api/tenant/settings'),
  updateSettings: (data) => apiRequest('/api/tenant/settings', { method: 'PUT', body: JSON.stringify(data) }),
  getTenantProfile: () => apiRequest('/api/tenant/profile'),
  getActivityLog: () => apiRequest('/api/tenant/activity'),
};

// ==================== SUPER ADMIN APIs ====================
export const superAdminApi = {
  getTenants: () => apiRequest('/api/super/tenants'),
  createTenant: (data) => apiRequest('/api/super/tenants', { method: 'POST', body: JSON.stringify(data) }),
  getTenantDetails: (id) => apiRequest(`/api/super/tenants/${id}`),
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
      localStorage.removeItem('api_key');
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
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
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

export const publicApi = {
  getTenantSettings: (tenantId) => {
    return fetch(`${API_BASE_URL}/api/tenant/settings/public?tenant_id=${tenantId}`)
      .then(async (response) => {
        if (!response.ok) {
          console.warn(`Failed to fetch settings for tenant ${tenantId}, using defaults`);
          return {
            office_start_time: "09:00:00",
            office_end_time: "18:00:00",
            late_threshold_minutes: 15,
            min_working_hours: 9.0,
            working_days: "1,2,3,4,5"
          };
        }
        return response.json();
      })
      .catch(() => ({
        office_start_time: "09:00:00",
        office_end_time: "18:00:00",
        late_threshold_minutes: 15,
        min_working_hours: 9.0,
        working_days: "1,2,3,4,5"
      }));
  }
};




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
  public:publicApi,
  tenantTasks: tenantTaskApi,
  orgTasks: orgTaskApi,
  employeeTasks: employeeTaskApi,
};



