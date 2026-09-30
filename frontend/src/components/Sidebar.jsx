// src/components/Sidebar.jsx
import React from 'react';
import { Link, NavLink } from 'react-router-dom';
import { Building2, ChevronsUpDown, Key, LayoutGrid, Lock, LogOut, Monitor } from 'lucide-react';
import { 
  BarChart3, 
  Calendar, 
  Cpu, 
  Activity, 
  Settings,
  ShieldCheck,
  Package,
  Clock,
  LayoutDashboard,
  UserCircle,
  FileText,
  Shield,
  Users,
  Send,
  Briefcase,
  CheckSquare,
  CodeSquare as Github,
  KeyRound,
  Network,
  ScrollText,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { getActingTenantName } from '../services/api';
import { isSuperAdmin, PLATFORM_HOME } from '../utils/roles';

// The tenant screens, shared by a Tenant Admin and by a Super Admin working
// inside an organisation.
const TENANT_ITEMS = [
  { icon: <BarChart3 size={18} />, label: 'Dashboard', path: '/super/dashboard' },
  { icon: <Users size={18} />, label: 'Employees', path: '/super/employees' },
  { icon: <Package size={18} />, label: 'Departments', path: '/super/departments' },
  { icon: <Shield size={18} />, label: 'Org Admins', path: '/super/org-admins' },
  { icon: <Clock size={18} />, label: 'Attendance', path: '/super/attendance' },
  { icon: <Briefcase size={18} />, label: 'Leaves', path: '/super/leaves' },
  { icon: <Calendar size={18} />, label: 'Holidays', path: '/super/holidays' },
  { icon: <Cpu size={18} />, label: 'Devices', path: '/super/devices' },
  { icon: <Send size={18} />, label: 'Device Commands', path: '/super/device-commands' },
  { icon: <CheckSquare size={18} />, label: 'Tasks', path: '/super/tasks' },
  { icon: <Github size={18} />, label: 'GitHub Repos', path: '/super/github-repos' },
  { icon: <Settings size={18} />, label: 'Settings', path: '/super/settings' },
];

const Sidebar = ({ role, label, iconColor }) => {
  const actingTenantName = getActingTenantName();
  const { logout, user } = useAuth();
  const superAdmin = isSuperAdmin(user);

  const getNavItems = () => {
    // The platform operator. Their own screens come first; the organisation's
    // screens appear only once one is chosen, since every one of them is
    // scoped to it and would otherwise just bounce to the chooser.
    //
    // Two things a Tenant Admin has that a Super Admin does not:
    //  * the vault — personal credentials inside one organisation, scoped to
    //    the caller's own tenant, which a Super Admin does not have;
    //  * Change API Key — rotation lives on the Organisations screen, which
    //    issues the key, shows it once and audits it. One place, not two.
    if (role === 'superadmin' && superAdmin) {
      const items = [
        { section: 'Platform' },
        { icon: <LayoutGrid size={18} />, label: 'Organisations', path: PLATFORM_HOME },
      ];
      if (actingTenantName) {
        items.push({ section: 'Organisation' }, ...TENANT_ITEMS);
      } else {
        items.push({ icon: <Building2 size={18} />, label: 'Choose organisation', path: '/choose-organisation' });
      }
      return items;
    }

    switch (role) {
      case 'superadmin':
        return [
          { icon: <BarChart3 size={18} />, label: 'Dashboard', path: '/super/dashboard' },
          { icon: <Users size={18} />, label: 'Employees', path: '/super/employees' },
          { icon: <Package size={18} />, label: 'Departments', path: '/super/departments' },
          { icon: <Shield size={18} />, label: 'Org Admins', path: '/super/org-admins' },
          { icon: <Clock size={18} />, label: 'Attendance', path: '/super/attendance' },
          { icon: <Briefcase size={18} />, label: 'Leaves', path: '/super/leaves' },
          { icon: <Calendar size={18} />, label: 'Holidays', path: '/super/holidays' },
          { icon: <Cpu size={18} />, label: 'Devices', path: '/super/devices' },
          { icon: <Send size={18} />, label: 'Device Commands', path: '/super/device-commands' },
          { icon: <CheckSquare size={18} />, label: 'Tasks', path: '/super/tasks' },
          { icon: <Github size={18} />, label: 'GitHub Repos', path: '/super/github-repos' },
          { icon: <Key size={18} />, label: 'Change API Key', path: '/super/change-api-key' },
          { icon: <Settings size={18} />, label: 'Settings', path: '/super/settings' },
          // Credential vault. Tenant Admin now holds credential.reveal too —
          // the old restriction assumed an API key with no second factor, and
          // this role signs in with a password and enrols an authenticator
          // like anyone else. Reveal is still gated by step-up MFA, which an
          // API-key caller cannot satisfy. Migration a6b7c8d9e0f1.
          { section: 'Credential Vault' },
          { icon: <KeyRound size={18} />, label: 'Vault', path: '/vault' },
          { icon: <Network size={18} />, label: 'Dependencies', path: '/vault/dependencies' },
          { icon: <ScrollText size={18} />, label: 'Audit Log', path: '/vault/audit' },
        ];
      case 'orgadmin':
        return [
          { icon: <LayoutDashboard size={18} />, label: 'Dashboard', path: '/org/dashboard' },
          { icon: <Users size={18} />, label: 'All Employees', path: '/org/employees' },
          { icon: <Clock size={18} />, label: 'Attendance List', path: '/org/attendance' },
          { icon: <Activity size={18} />, label: 'Today Attendance', path: '/org/today' },
          { icon: <Briefcase size={18} />, label: 'Leave Requests', path: '/org/leaves' },
          { icon: <BarChart3 size={18} />, label: 'Attendance Report', path: '/org/report-att' },
          { icon: <FileText size={18} />, label: 'Leave Report', path: '/org/report-leave' },
          { icon: <Cpu size={18} />, label: 'Devices', path: '/org/devices' },
          { icon: <CheckSquare size={18} />, label: 'Tasks', path: '/org/tasks' },
          { icon: <Monitor size={18} />, label: 'Activity Tracker', path: '/org/tracker' },
          { icon: <Lock size={18} />, label: 'Change Password', path: '/org/change-password' },
          { section: 'Credential Vault' },
          { icon: <KeyRound size={18} />, label: 'Vault', path: '/vault' },
          { icon: <Network size={18} />, label: 'Dependencies', path: '/vault/dependencies' },
          { icon: <ScrollText size={18} />, label: 'Audit Log', path: '/vault/audit' },
        ];
      case 'user':
        return [
          { icon: <LayoutDashboard size={18} />, label: 'Dashboard', path: '/emp/dashboard' },
          { icon: <Clock size={18} />, label: 'Attendance List', path: '/emp/attendance' },
          { icon: <Briefcase size={18} />, label: 'Leave List', path: '/emp/leaves' },
          { icon: <CheckSquare size={18} />, label: 'My Tasks', path: '/emp/tasks' },
          { icon: <Calendar size={18} />, label: 'Holidays', path: '/emp/holidays' },
          { icon: <UserCircle size={18} />, label: 'Profile', path: '/emp/profile' },
          // Employees get the vault and the dependency map, but not the audit
          // log — that needs `audit.view`, which their role does not carry.
          { section: 'Credential Vault' },
          { icon: <KeyRound size={18} />, label: 'My Vault', path: '/vault' },
          { icon: <Network size={18} />, label: 'Dependencies', path: '/vault/dependencies' },
        ];
      default:
        return [];
    }
  };

  const navItems = getNavItems();

  return (
    <aside className="sidebar" id="sidebar">
      <div className="sb-header">
        <div className="sb-logo" style={{ background: iconColor }}>
          <ShieldCheck color="white" size={20} />
        </div>
        <div>
          <div className="sb-title">Sentinel</div>
          <div className="sb-role">{label}</div>
        </div>
      </div>

      {/* Which organisation a Super Admin is acting within, and how to change
          it. Shown only for them — a tenant admin has exactly one organisation
          and no choice to make, so the control would be noise. Stating it
          permanently matters here: every screen below is scoped to this
          organisation, and acting on the wrong one is an easy mistake to make
          and a hard one to notice. */}
      {superAdmin && actingTenantName && (
        <Link
          to="/choose-organisation"
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            margin: '0.6rem 0.75rem 0', padding: '0.5rem 0.7rem',
            background: 'var(--bg3)', border: '1px solid var(--border)',
            borderRadius: 8, textDecoration: 'none', color: 'var(--text2)',
          }}
          title="Switch organisation"
        >
          <Building2 size={14} style={{ flexShrink: 0, color: 'var(--purple)' }} />
          <span style={{ flex: 1, minWidth: 0, fontSize: '0.78rem', fontWeight: 500,
            color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis',
            whiteSpace: 'nowrap' }}>
            {actingTenantName}
          </span>
          <ChevronsUpDown size={13} style={{ flexShrink: 0 }} />
        </Link>
      )}


      <div style={{ flex: 1, padding: '0.5rem 0' }}>
        {navItems.map((item, idx) => (
          // A `section` entry is a heading, not a link. Handled here rather
          // than by splitting the array so each role's menu stays one ordered
          // list that reads in the order it renders.
          item.section ? (
            <div
              key={idx}
              style={{
                padding: '1rem 1.1rem 0.35rem',
                fontSize: '0.64rem',
                letterSpacing: '0.09em',
                textTransform: 'uppercase',
                opacity: 0.45,
                fontFamily: 'var(--mono)',
              }}
            >
              {item.section}
            </div>
          ) : (
            <NavLink
              key={idx}
              to={item.path}
              className={({ isActive }) => `sb-item ${isActive ? `active ${role === 'superadmin' ? 'super' : role === 'user' ? 'emp' : ''}` : ''}`}
            >
              <span className="sb-icon">{item.icon}</span>
              {item.label}
            </NavLink>
          )
        ))}
      </div>

      <div className="sb-signout-wrapper">
        <button onClick={logout} className="sb-signout" style={{ background: 'none', border: 'none', width: '100%', cursor: 'pointer' }}>
          <LogOut size={16} style={{ marginRight: '8px' }} />
          Sign Out
        </button>
      </div>
    </aside>
  );
};

export default Sidebar;