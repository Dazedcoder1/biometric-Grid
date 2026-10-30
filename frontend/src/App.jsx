// src/App.jsx
import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider } from './context/ThemeContext';
import { AuthProvider } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import Login from './pages/Login';
import ChooseOrganisation from './pages/super/ChooseOrganisation';
import Organisations from './pages/super/Organisations';
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

// Credential Vault
import VaultCredentials from './pages/vault/Credentials';
import VaultCredentialDetail from './pages/vault/CredentialDetail';
import VaultAuditLog from './pages/vault/AuditLog';
import VaultDependencyMap from './pages/vault/DependencyMap';
import VaultPeople from './pages/vault/People';
import ChangePasswordRequired from './pages/ChangePasswordRequired';
import MyClockLog from './pages/clock/MyClockLog';
import TeamClock from './pages/clock/TeamClock';
import PayrollRuns from './pages/payroll/PayrollRuns';
import PayrollRun from './pages/payroll/PayrollRun';
import PayrollPeople from './pages/payroll/PayrollPeople';
import PayComponents from './pages/payroll/PayComponents';
import Reimbursements from './pages/payroll/Reimbursements';
import MyPay from './pages/payroll/MyPay';
import Letters from './pages/documents/Letters';
import LetterTemplates from './pages/documents/LetterTemplates';
import Policies from './pages/documents/Policies';
import EmployeeFiles from './pages/documents/EmployeeFiles';
import MyDocuments from './pages/documents/MyDocuments';
import OrgTree from './pages/org/OrgTree';
import MyDay from './pages/reporting/MyDay';
import TeamReports from './pages/reporting/TeamReports';
import Targets from './pages/reporting/Targets';

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <Router>
          <Routes>
            {/* Public routes.
                One sign-in form for all three roles — the server decides what
                you are, so there is nothing to pick first. The old per-role
                paths redirect rather than 404, because they are in people's
                bookmarks and in the output of create_organisation.py. */}
            <Route path="/" element={<Login />} />
            <Route path="/login" element={<Login />} />
            {/* The HR portal: same accounts, lands on payroll, HR access required. */}
            <Route path="/hr/login" element={<Login portal="hr" />} />
            <Route path="/login/:role" element={<Navigate to="/login" replace />} />

            {/* ==================== PLATFORM (SUPER ADMIN) ==================== */}
            {/* Every organisation, from above: create, rename, rotate keys,
                delete when empty, and pick one to work in. Where a Super Admin
                lands after signing in. */}
            <Route
              path="/platform/organisations"
              element={(
                <ProtectedRoute superAdminOnly>
                  <Organisations />
                </ProtectedRoute>
              )}
            />
            {/* The quick switcher behind the organisation name in the sidebar,
                and where /super/* sends a Super Admin with none chosen. */}
            <Route
              path="/choose-organisation"
              element={(
                <ProtectedRoute superAdminOnly>
                  <ChooseOrganisation />
                </ProtectedRoute>
              )}
            />

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

            {/* ==================== PAYROLL ==================== */}
            <Route
              path="/payroll"
              element={
                <ProtectedRoute allowedRoles={['tenant_admin', 'superadmin']} allowHr>
                  <PayrollRuns />
                </ProtectedRoute>
              }
            />
            <Route
              path="/payroll/runs/:id"
              element={
                <ProtectedRoute allowedRoles={['tenant_admin', 'superadmin']} allowHr>
                  <PayrollRun />
                </ProtectedRoute>
              }
            />
            <Route
              path="/payroll/people"
              element={
                <ProtectedRoute allowedRoles={['tenant_admin', 'superadmin']} allowHr>
                  <PayrollPeople />
                </ProtectedRoute>
              }
            />
            <Route
              path="/payroll/components"
              element={
                <ProtectedRoute allowedRoles={['tenant_admin', 'superadmin']} allowHr>
                  <PayComponents />
                </ProtectedRoute>
              }
            />
            {/* Org Admins decide their own department's claims. */}
            <Route
              path="/payroll/claims"
              element={
                <ProtectedRoute allowedRoles={['tenant_admin', 'superadmin', 'org_admin', 'department_admin']} allowHr>
                  <Reimbursements />
                </ProtectedRoute>
              }
            />
            {/* Anyone's own payslips, salary history and claims. */}
            <Route
              path="/my-pay"
              element={
                <ProtectedRoute allowedRoles={['employee', 'user', 'org_admin', 'department_admin', 'tenant_admin']}>
                  <MyPay />
                </ProtectedRoute>
              }
            />

            {/* ==================== REPORTING & TARGETS ==================== */}
            <Route path="/my-day" element={<ProtectedRoute allowedRoles={['tenant_admin', 'superadmin', 'org_admin', 'department_admin', 'employee', 'user']}><MyDay /></ProtectedRoute>} />
            <Route path="/reporting/targets" element={<ProtectedRoute allowedRoles={['tenant_admin', 'superadmin', 'org_admin', 'department_admin', 'employee', 'user']}><Targets /></ProtectedRoute>} />
            <Route path="/reporting/team" element={<ProtectedRoute allowedRoles={['tenant_admin', 'superadmin', 'org_admin', 'department_admin']} allowHr><TeamReports /></ProtectedRoute>} />

            {/* ==================== ORGANISATION TREE ==================== */}
            {/* Every role; the server decides how much of the tree each sees. */}
            <Route
              path="/organisation"
              element={
                <ProtectedRoute allowedRoles={['tenant_admin', 'superadmin', 'org_admin', 'department_admin', 'employee', 'user']}>
                  <OrgTree />
                </ProtectedRoute>
              }
            />

            {/* ==================== HR DOCUMENTS & LETTERS ==================== */}
            <Route
              path="/documents/letters"
              element={
                <ProtectedRoute allowedRoles={['tenant_admin', 'superadmin']} allowHr>
                  <Letters />
                </ProtectedRoute>
              }
            />
            <Route
              path="/documents/templates"
              element={
                <ProtectedRoute allowedRoles={['tenant_admin', 'superadmin']} allowHr>
                  <LetterTemplates />
                </ProtectedRoute>
              }
            />
            <Route
              path="/documents/policies"
              element={
                <ProtectedRoute allowedRoles={['tenant_admin', 'superadmin']} allowHr>
                  <Policies />
                </ProtectedRoute>
              }
            />
            <Route
              path="/documents/files"
              element={
                <ProtectedRoute allowedRoles={['tenant_admin', 'superadmin']} allowHr>
                  <EmployeeFiles />
                </ProtectedRoute>
              }
            />
            <Route
              path="/my-documents"
              element={
                <ProtectedRoute allowedRoles={['employee', 'user', 'org_admin', 'department_admin']}>
                  <MyDocuments />
                </ProtectedRoute>
              }
            />

            {/* ==================== SIGN-IN CLOCK ==================== */}
            {/* Web Sign In / Sign Out, merged with the fingerprint scanners. */}
            <Route
              path="/super/clock-team"
              element={
                <ProtectedRoute allowedRoles={['tenant_admin', 'superadmin']}>
                  <TeamClock scope="tenant" />
                </ProtectedRoute>
              }
            />
            <Route
              path="/org/clock-team"
              element={
                <ProtectedRoute allowedRoles={['org_admin', 'department_admin']}>
                  <TeamClock scope="org" />
                </ProtectedRoute>
              }
            />
            <Route
              path="/org/my-clock"
              element={
                <ProtectedRoute allowedRoles={['org_admin', 'department_admin']}>
                  <MyClockLog />
                </ProtectedRoute>
              }
            />
            <Route
              path="/emp/clock"
              element={
                <ProtectedRoute allowedRoles={['employee', 'user']}>
                  <MyClockLog />
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

            {/* Credential Vault — every signed-in role has a personal vault.
                What each can actually see is decided by permissions on the
                server; this route only controls which roles get the screen. */}
            <Route
              path="/vault"
              element={
                <ProtectedRoute
                  allowedRoles={['employee', 'user', 'org_admin', 'department_admin', 'tenant_admin']}
                >
                  <VaultCredentials />
                </ProtectedRoute>
              }
            />
            <Route
              path="/vault/credential/:id"
              element={
                <ProtectedRoute
                  allowedRoles={['employee', 'user', 'org_admin', 'department_admin', 'tenant_admin']}
                >
                  <VaultCredentialDetail />
                </ProtectedRoute>
              }
            />
            {/* The audit log is gated server-side on the `audit.view`
                permission; this list only decides who gets the screen. */}
            <Route
              path="/vault/audit"
              element={
                <ProtectedRoute allowedRoles={['tenant_admin', 'org_admin']}>
                  <VaultAuditLog />
                </ProtectedRoute>
              }
            />

            {/* Everyone's vault, for the people who administer them: a Tenant
                Admin sees their organisation, an Org Admin their department.
                The server decides who is listed; this only gates the screen. */}
            <Route
              path="/vault/people"
              element={
                <ProtectedRoute allowedRoles={['tenant_admin', 'org_admin']}>
                  <VaultPeople />
                </ProtectedRoute>
              }
            />

            {/* After an admin issues a temporary password. Any signed-in role;
                ProtectedRoute sends people here until they choose their own. */}
            <Route
              path="/change-password"
              element={
                <ProtectedRoute>
                  <ChangePasswordRequired />
                </ProtectedRoute>
              }
            />

            <Route
              path="/vault/dependencies"
              element={
                <ProtectedRoute
                  allowedRoles={['employee', 'user', 'org_admin', 'department_admin', 'tenant_admin']}
                >
                  <VaultDependencyMap />
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