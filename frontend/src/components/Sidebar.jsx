// src/components/Sidebar.jsx
import React from 'react';
import { Link, NavLink } from 'react-router-dom';
import {
  Building2, ChevronsUpDown, IndianRupee, Key, LayoutGrid, Lock, LogIn, LogOut, Monitor, Receipt,
  ClipboardList, FileSignature, FolderOpen, Files, GitFork, Goal, Sunset, ScrollText as PolicyIcon, SlidersHorizontal, Stamp, Timer, Wallet,
} from 'lucide-react';
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
  { icon: <Timer size={18} />, label: 'Sign-ins', path: '/super/clock-team' },
  { icon: <Briefcase size={18} />, label: 'Leaves', path: '/super/leaves' },
  { icon: <Calendar size={18} />, label: 'Holidays', path: '/super/holidays' },
  { icon: <Cpu size={18} />, label: 'Devices', path: '/super/devices' },
  { icon: <Send size={18} />, label: 'Device Commands', path: '/super/device-commands' },
  { icon: <CheckSquare size={18} />, label: 'Tasks', path: '/super/tasks' },
  { icon: <Github size={18} />, label: 'GitHub Repos', path: '/super/github-repos' },
  { icon: <Settings size={18} />, label: 'Settings', path: '/super/settings' },
  { section: 'Payroll' },
  { icon: <IndianRupee size={18} />, label: 'Payroll Runs', path: '/payroll' },
  { icon: <Wallet size={18} />, label: 'Salaries', path: '/payroll/people' },
  { icon: <SlidersHorizontal size={18} />, label: 'Pay Components', path: '/payroll/components' },
  { icon: <Receipt size={18} />, label: 'Expense Claims', path: '/payroll/claims' },
  { section: 'Documents' },
  { icon: <FileSignature size={18} />, label: 'Letters', path: '/documents/letters' },
  { icon: <Stamp size={18} />, label: 'Letter Templates', path: '/documents/templates' },
  { icon: <PolicyIcon size={18} />, label: 'Policies & Handbook', path: '/documents/policies' },
  { icon: <FolderOpen size={18} />, label: 'Employee Documents', path: '/documents/files' },
  { section: 'Reporting' },
  { icon: <ClipboardList size={18} />, label: 'Team Reports', path: '/reporting/team' },
  { icon: <Goal size={18} />, label: 'Targets', path: '/reporting/targets' },
];

const Sidebar = ({ role, label, iconColor }) => {
  const actingTenantName = getActingTenantName();
  const { logout, user } = useAuth();
  const superAdmin = isSuperAdmin(user);

  // Employees and Org Admins with HR access get payroll for the whole
  // organisation, on top of their own menu.
  const HR_ITEMS = user?.isHr ? [
    { section: 'HR' },
    { icon: <IndianRupee size={18} />, label: 'Payroll Runs', path: '/payroll' },
    { icon: <Wallet size={18} />, label: 'Salaries', path: '/payroll/people' },
    { icon: <SlidersHorizontal size={18} />, label: 'Pay Components', path: '/payroll/components' },
    { icon: <Receipt size={18} />, label: 'Expense Claims', path: '/payroll/claims' },
    { icon: <FileSignature size={18} />, label: 'Letters', path: '/documents/letters' },
    { icon: <Stamp size={18} />, label: 'Letter Templates', path: '/documents/templates' },
    { icon: <PolicyIcon size={18} />, label: 'Policies & Handbook', path: '/documents/policies' },
    { icon: <FolderOpen size={18} />, label: 'Employee Documents', path: '/documents/files' },
  ] : [];

  const getNavItems = () => {
    // The platform operator: full control. Their own screens come first; the
    // organisation's screens appear once one is chosen, since each is scoped
    // to it and would otherwise just bounce to the chooser.
    //
    // The vault section is People (everyone's vaults — reveal, change, reset
    // sign-in passwords), the Dependency Map and the Audit Log. Not a personal
    // vault: a vault belongs to an organisation and a Super Admin has none.
    // Change API Key is absent too — rotation lives on Organisations, which
    // issues the key, shows it once and audits it. One place, not two.
    if (role === 'superadmin' && superAdmin) {
      const items = [
        { section: 'Platform' },
        { icon: <LayoutGrid size={18} />, label: 'Organisations', path: PLATFORM_HOME },
        // Every organisation, its admins, departments and people.
        { icon: <GitFork size={18} />, label: 'Organisation Tree', path: '/organisation' },
        // Works with or without an organisation chosen: without one it shows
        // every organisation's activity.
        { icon: <ScrollText size={18} />, label: 'Audit Log', path: '/vault/audit' },
      ];
      if (actingTenantName) {
        items.push(
          { section: 'Organisation' },
          ...TENANT_ITEMS,
          { section: 'Credential Vault' },
          { icon: <Users size={18} />, label: 'People', path: '/vault/people' },
          { icon: <Network size={18} />, label: 'Dependencies', path: '/vault/dependencies' },
        );
      } else {
        items.push({ icon: <Building2 size={18} />, label: 'Choose organisation', path: '/choose-organisation' });
      }
      return items;
    }

    switch (role) {
      case 'superadmin':
        return [
          { icon: <BarChart3 size={18} />, label: 'Dashboard', path: '/super/dashboard' },
          { icon: <GitFork size={18} />, label: 'Organisation Tree', path: '/organisation' },
          { icon: <Users size={18} />, label: 'Employees', path: '/super/employees' },
          { icon: <Package size={18} />, label: 'Departments', path: '/super/departments' },
          { icon: <Shield size={18} />, label: 'Org Admins', path: '/super/org-admins' },
          { icon: <Clock size={18} />, label: 'Attendance', path: '/super/attendance' },
          { icon: <Timer size={18} />, label: 'Sign-ins', path: '/super/clock-team' },
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
          { section: 'Payroll' },
          { icon: <IndianRupee size={18} />, label: 'Payroll Runs', path: '/payroll' },
          { icon: <Wallet size={18} />, label: 'Salaries', path: '/payroll/people' },
          { icon: <SlidersHorizontal size={18} />, label: 'Pay Components', path: '/payroll/components' },
          { icon: <Receipt size={18} />, label: 'Expense Claims', path: '/payroll/claims' },
          { section: 'Documents' },
          { icon: <FileSignature size={18} />, label: 'Letters', path: '/documents/letters' },
          { icon: <Stamp size={18} />, label: 'Letter Templates', path: '/documents/templates' },
          { icon: <PolicyIcon size={18} />, label: 'Policies & Handbook', path: '/documents/policies' },
          { icon: <FolderOpen size={18} />, label: 'Employee Documents', path: '/documents/files' },
          { section: 'Reporting' },
          { icon: <ClipboardList size={18} />, label: 'Team Reports', path: '/reporting/team' },
          { icon: <Goal size={18} />, label: 'Targets', path: '/reporting/targets' },
          { section: 'Credential Vault' },
          { icon: <KeyRound size={18} />, label: 'Vault', path: '/vault' },
          // Everyone in the organisation, one vault at a time.
          { icon: <Users size={18} />, label: 'People', path: '/vault/people' },
          { icon: <Network size={18} />, label: 'Dependencies', path: '/vault/dependencies' },
          { icon: <ScrollText size={18} />, label: 'Audit Log', path: '/vault/audit' },
        ];
      case 'orgadmin':
        return [
          { icon: <LayoutDashboard size={18} />, label: 'Dashboard', path: '/org/dashboard' },
          { icon: <GitFork size={18} />, label: 'Organisation Tree', path: '/organisation' },
          { icon: <Timer size={18} />, label: 'Team Sign-ins', path: '/org/clock-team' },
          { icon: <LogIn size={18} />, label: 'My Sign-in Log', path: '/org/my-clock' },
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
          { section: 'Payroll' },
          { icon: <Wallet size={18} />, label: 'My Pay', path: '/my-pay' },
          { icon: <Files size={18} />, label: 'My Documents', path: '/my-documents' },
          { section: 'Reporting' },
          { icon: <Sunset size={18} />, label: 'My Day', path: '/my-day' },
          { icon: <ClipboardList size={18} />, label: 'Team Reports', path: '/reporting/team' },
          { icon: <Goal size={18} />, label: 'Targets', path: '/reporting/targets' },
          ...(user?.isHr ? HR_ITEMS.slice(1) : [
            { icon: <Receipt size={18} />, label: 'Expense Claims', path: '/payroll/claims' },
          ]),
          { section: 'Credential Vault' },
          { icon: <KeyRound size={18} />, label: 'Vault', path: '/vault' },
          // The employees in their own department.
          { icon: <Users size={18} />, label: 'People', path: '/vault/people' },
          { icon: <Network size={18} />, label: 'Dependencies', path: '/vault/dependencies' },
          { icon: <ScrollText size={18} />, label: 'Audit Log', path: '/vault/audit' },
        ];
      case 'user':
        return [
          { icon: <LayoutDashboard size={18} />, label: 'Dashboard', path: '/emp/dashboard' },
          { icon: <GitFork size={18} />, label: 'Organisation Tree', path: '/organisation' },
          { icon: <LogIn size={18} />, label: 'Sign In / Out', path: '/emp/clock' },
          { icon: <Clock size={18} />, label: 'Attendance List', path: '/emp/attendance' },
          { icon: <Briefcase size={18} />, label: 'Leave List', path: '/emp/leaves' },
          { icon: <CheckSquare size={18} />, label: 'My Tasks', path: '/emp/tasks' },
          { icon: <Calendar size={18} />, label: 'Holidays', path: '/emp/holidays' },
          { icon: <UserCircle size={18} />, label: 'Profile', path: '/emp/profile' },
          // Employees get the vault and the dependency map, but not the audit
          // log — that needs `audit.view`, which their role does not carry.
          { icon: <Wallet size={18} />, label: 'My Pay', path: '/my-pay' },
          { icon: <Files size={18} />, label: 'My Documents', path: '/my-documents' },
          { section: 'Reporting' },
          { icon: <Sunset size={18} />, label: 'My Day', path: '/my-day' },
          { icon: <Goal size={18} />, label: 'My Targets', path: '/reporting/targets' },
          ...HR_ITEMS,
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
              // Exact match when another item lives underneath this one, so
              // "Payroll Runs" (/payroll) is not lit up on /payroll/people.
              end={navItems.some((o) => o.path && o.path !== item.path && o.path.startsWith(`${item.path}/`))}
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