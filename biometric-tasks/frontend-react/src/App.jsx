// src/App.jsx
import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider } from './context/ThemeContext';
import { AuthProvider } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import Gateway from './pages/Gateway';
import Login from './pages/Login';
import ChangeApiKey from './pages/tenant/ChangeApiKey';
import OrgTracker from './pages/org/Tracker';

// Tenant Imports
import TenantDash from './pages/tenant/Dashboard';
import TenantDepts from './pages/tenant/Departments';
import TenantEmployees from './pages/tenant/Employees';
import TenantAttendance from './pages/tenant/Attendance';
import TenantLeaves from './pages/tenant/Leaves';
import TenantHolidays from './pages/tenant/Holidays';
import TenantDevices from './pages/tenant/Devices';
import TenantDeviceCommands from './pages/tenant/DeviceCommands';
import TenantOrgAdmins from './pages/tenant/OrgAdmins';
import TenantActivity from './pages/tenant/Activity';
import TenantSettings from './pages/tenant/Settings';

// Org Imports
import OrgDash from './pages/org/Dashboard';
import OrgEmployees from './pages/org/Employees';
import OrgAttendance from './pages/org/Attendance';
import OrgToday from './pages/org/Today';
import OrgLeaves from './pages/org/Leaves';
import OrgReportAtt from './pages/org/ReportAtt';
import OrgReportLeave from './pages/org/ReportLeave';
import OrgDevices from './pages/org/OrgDevices';
import OrgActivity from './pages/org/Activity';
import OrgChangePassword from './pages/org/ChangePassword';  // ✅ ADDED

// Employee Imports
import EmpDash from './pages/employee/Dashboard';
import EmpAttendance from './pages/employee/Attendance';
import EmpLeaves from './pages/employee/Leaves';
import EmpHolidays from './pages/employee/Holidays';
import EmpProfile from './pages/employee/Profile';

// Task Manager Imports
import TenantTasks from './pages/tenant/Tasks';
import TenantGitHubRepos from './pages/tenant/GitHubRepos';
import OrgTasks from './pages/org/Tasks';
import EmpTasks from './pages/employee/Tasks';

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <Router>
          <Routes>
            {/* Public routes */}
            <Route path="/" element={<Gateway />} />
            <Route path="/login/:role" element={<Login />} />

            {/* ==================== TENANT ADMIN ROUTES ==================== */}
            <Route 
              path="/super/dashboard" 
              element={
                <ProtectedRoute allowedRoles={['tenant_admin', 'superadmin']}>
                  <TenantDash />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/super/employees" 
              element={
                <ProtectedRoute allowedRoles={['tenant_admin', 'superadmin']}>
                  <TenantEmployees />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/super/departments" 
              element={
                <ProtectedRoute allowedRoles={['tenant_admin', 'superadmin']}>
                  <TenantDepts />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/super/org-admins" 
              element={
                <ProtectedRoute allowedRoles={['tenant_admin', 'superadmin']}>
                  <TenantOrgAdmins />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/super/attendance" 
              element={
                <ProtectedRoute allowedRoles={['tenant_admin', 'superadmin']}>
                  <TenantAttendance />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/super/leaves" 
              element={
                <ProtectedRoute allowedRoles={['tenant_admin', 'superadmin']}>
                  <TenantLeaves />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/super/holidays" 
              element={
                <ProtectedRoute allowedRoles={['tenant_admin', 'superadmin']}>
                  <TenantHolidays />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/super/devices" 
              element={
                <ProtectedRoute allowedRoles={['tenant_admin', 'superadmin']}>
                  <TenantDevices />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/super/device-commands" 
              element={
                <ProtectedRoute allowedRoles={['tenant_admin', 'superadmin']}>
                  <TenantDeviceCommands />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/super/activity" 
              element={
                <ProtectedRoute allowedRoles={['tenant_admin', 'superadmin']}>
                  <TenantActivity />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/super/settings" 
              element={
                <ProtectedRoute allowedRoles={['tenant_admin', 'superadmin']}>
                  <TenantSettings />
                </ProtectedRoute>
              } 
            />
            {/* ✅ NEW: Change API Key Route */}
            <Route 
              path="/super/change-api-key" 
              element={
                <ProtectedRoute allowedRoles={['tenant_admin', 'superadmin']}>
                  <ChangeApiKey />
                </ProtectedRoute>
              } 
            />

            {/* ==================== ORG ADMIN ROUTES ==================== */}
            <Route 
              path="/org/dashboard" 
              element={
                <ProtectedRoute allowedRoles={['org_admin', 'department_admin']}>
                  <OrgDash />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/org/employees" 
              element={
                <ProtectedRoute allowedRoles={['org_admin', 'department_admin']}>
                  <OrgEmployees />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/org/attendance" 
              element={
                <ProtectedRoute allowedRoles={['org_admin', 'department_admin']}>
                  <OrgAttendance />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/org/today" 
              element={
                <ProtectedRoute allowedRoles={['org_admin', 'department_admin']}>
                  <OrgToday />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/org/leaves" 
              element={
                <ProtectedRoute allowedRoles={['org_admin', 'department_admin']}>
                  <OrgLeaves />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/org/report-att" 
              element={
                <ProtectedRoute allowedRoles={['org_admin', 'department_admin']}>
                  <OrgReportAtt />
                </ProtectedRoute>
              } 
            />
                      <Route 
            path="/org/tracker" 
            element={
              <ProtectedRoute allowedRoles={['org_admin', 'department_admin']}>
                <OrgTracker />
              </ProtectedRoute>
            } 
          />
            <Route 
              path="/org/report-leave" 
              element={
                <ProtectedRoute allowedRoles={['org_admin', 'department_admin']}>
                  <OrgReportLeave />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/org/devices" 
              element={
                <ProtectedRoute allowedRoles={['org_admin', 'department_admin']}>
                  <OrgDevices />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/org/activity" 
              element={
                <ProtectedRoute allowedRoles={['org_admin', 'department_admin']}>
                  <OrgActivity />
                </ProtectedRoute>
              } 
            />
            {/* ✅ NEW: Org Admin Change Password Route */}
            <Route 
              path="/org/change-password" 
              element={
                <ProtectedRoute allowedRoles={['org_admin', 'department_admin']}>
                  <OrgChangePassword />
                </ProtectedRoute>
              } 
            />

            {/* ==================== EMPLOYEE ROUTES ==================== */}
            <Route 
              path="/emp/dashboard" 
              element={
                <ProtectedRoute allowedRoles={['employee', 'user']}>
                  <EmpDash />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/emp/attendance" 
              element={
                <ProtectedRoute allowedRoles={['employee', 'user']}>
                  <EmpAttendance />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/emp/leaves" 
              element={
                <ProtectedRoute allowedRoles={['employee', 'user']}>
                  <EmpLeaves />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/emp/holidays" 
              element={
                <ProtectedRoute allowedRoles={['employee', 'user']}>
                  <EmpHolidays />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/emp/profile" 
              element={
                <ProtectedRoute allowedRoles={['employee', 'user']}>
                  <EmpProfile />
                </ProtectedRoute>
              } 
            />

            {/* ─── Task Manager ─────────────────────────────────── */}
            <Route
              path="/super/tasks"
              element={
                <ProtectedRoute allowedRoles={['tenant_admin', 'superadmin']}>
                  <TenantTasks />
                </ProtectedRoute>
              }
            />
            <Route
              path="/super/github-repos"
              element={
                <ProtectedRoute allowedRoles={['tenant_admin', 'superadmin']}>
                  <TenantGitHubRepos />
                </ProtectedRoute>
              }
            />
            <Route
              path="/org/tasks"
              element={
                <ProtectedRoute allowedRoles={['org_admin', 'department_admin']}>
                  <OrgTasks />
                </ProtectedRoute>
              }
            />
            <Route
              path="/emp/tasks"
              element={
                <ProtectedRoute allowedRoles={['employee', 'user']}>
                  <EmpTasks />
                </ProtectedRoute>
              }
            />

            {/* Catch-all - redirect to home */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Router>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;