// src/services/trackerApi.js

// ============================================
// PRODUCTION API URL - Using attendance API domain
// ============================================
const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'https://api.attendance.gridsphere.in';

const getToken = () => localStorage.getItem('access_token');
const getApiKey = () => localStorage.getItem('api_key');
const getAuthType = () => localStorage.getItem('auth_type');

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
    throw new Error(error.detail || error.error || `API Error: ${response.status}`);
  }

  return response.json();
}

export const trackerApi = {
  // Get all employees in department with tracking data
  getEmployees: async () => {
    const response = await apiRequest('/api/tracker/employees');
    return response || [];
  },
  
  // Get employee details with sessions and screenshots
  getEmployeeDetails: async (userId) => {
    const response = await apiRequest(`/api/tracker/employee/${userId}`);
    return {
      id: response.id,
      name: response.name,
      email: response.email,
      employee_code: response.employee_code,
      department_name: response.department_name,
      hasActiveSession: response.hasActiveSession || false,
      sessionStart: response.sessionStart,
      totalWorkingHours: response.totalWorkingHours || 0,
      todayHours: response.todayHours || 0,
      totalSessions: response.totalSessions || 0,
      screenshotCount: response.screenshotCount || 0,
      sessions: response.sessions || []
    };
  },
  
  // Get screenshots for an employee
  getScreenshots: async (userId, limit = 50) => {
    const response = await apiRequest(`/api/tracker/screenshots/${userId}?limit=${limit}`);
    return response.screenshots || [];
  },
  
  // Get session history
  getSessions: async (userId) => {
    const response = await apiRequest(`/api/tracker/sessions/${userId}`);
    return response.sessions || [];
  },
  
  // Get real-time dashboard stats
  getDashboardStats: async () => {
    const response = await apiRequest('/api/tracker/dashboard');
    return {
      totalEmployees: response.totalEmployees || 0,
      activeEmployees: response.activeEmployees || 0,
      totalHoursToday: response.totalHoursToday || 0,
      totalScreenshots: response.totalScreenshots || 0,
      avgHoursPerEmployee: response.avgHoursPerEmployee || 0,
      complianceRate: response.complianceRate || 0,
      department_name: response.department_name || null
    };
  },
  
  // Get activity chart data (top performers by hours)
  getActivityData: async () => {
    const response = await apiRequest('/api/tracker/employees');
    const users = response || [];
    const topUsers = [...users]
      .sort((a, b) => (b.totalWorkingHours || 0) - (a.totalWorkingHours || 0))
      .slice(0, 6);
    
    return {
      labels: topUsers.map(u => (u.name || u.email || 'Unknown').substring(0, 14)),
      values: topUsers.map(u => u.totalWorkingHours || 0)
    };
  },
  
  // Get reports summary
  getReports: async () => {
    const response = await apiRequest('/api/tracker/reports');
    return response || [];
  },
};

export default trackerApi;