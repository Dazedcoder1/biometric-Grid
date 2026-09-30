// src/pages/super/ChooseOrganisation.jsx
//
// Which organisation a Super Admin is administering — the quick switcher.
//
// A Super Admin belongs to the platform, not to a tenant — `users.tenant_id`
// is NULL for these accounts by design. Every screen under /super is
// tenant-scoped, so this picks the organisation those screens act on. The
// choice is sent as X-Acting-Tenant-Id on every /api/tenant call and
// re-checked server-side, so it is a convenience for the client rather than a
// grant of access.
//
// Creating, renaming and deleting organisations live on the platform screen
// (/platform/organisations). This one only chooses.
//
// The route is superAdminOnly, so nobody else reaches this component.

import React, { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { AlertCircle, Building2, Check, LayoutGrid, LogOut, Search } from 'lucide-react';

import { useAuth } from '../../context/AuthContext';
import { superAdminApi, setActingTenant, getActingTenantId } from '../../services/api';
import { PLATFORM_HOME } from '../../utils/roles';
// .v-btn and .v-banner started life in the vault but are plain utilities; this
// screen uses them rather than growing a second set of the same rules.
import '../vault/vault.css';

export default function ChooseOrganisation() {
  const navigate = useNavigate();
  const location = useLocation();
  const { logout, user } = useAuth();

  const [tenants, setTenants] = useState(null);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('');

  const current = getActingTenantId();

  useEffect(() => {
    let cancelled = false;
    superAdminApi.getTenants()
      .then((rows) => { if (!cancelled) setTenants(rows); })
      .catch((err) => {
        if (!cancelled) setError(err.message || 'Could not load organisations.');
      });
    return () => { cancelled = true; };
  }, []);

  const choose = (tenant) => {
    setActingTenant(tenant);
    // Back to the tenant screen they were heading for, if that is what brought
    // them here; otherwise the dashboard. Replace, not push: the chooser should
    // not sit in history behind the dashboard, where Back would land on it
    // again with a selection already made and no obvious reason for being there.
    const from = location.state?.from;
    const target = typeof from === 'string' && from.startsWith('/super/') ? from : '/super/dashboard';
    navigate(target, { replace: true });
  };

  const visible = (tenants || []).filter((t) =>
    t.name.toLowerCase().includes(filter.trim().toLowerCase()));

  return (
    <div className="login-page">
      <div className="grid-bg" />

      <div className="login-container" style={{ maxWidth: 520 }}>
        <div className="login-card">
          <div className="login-header">
            <div className="login-logo-circle"
              style={{ background: 'rgba(168,85,247,0.12)', color: 'var(--purple)' }}>
              <Building2 size={30} />
            </div>
            <h2 className="login-title">Choose an organisation</h2>
            <p className="login-subtitle">
              Signed in as {user?.name || user?.email || 'Super Admin'}. Pick which
              organisation to work in — you can switch at any time from the sidebar.
            </p>
          </div>

          {error && (
            <div className="v-banner bad" role="alert">
              <AlertCircle size={14} />
              <span>{error}</span>
            </div>
          )}

          {tenants === null && !error && (
            <p style={{ fontSize: '.85rem', color: 'var(--text3)', textAlign: 'center' }}>
              Loading organisations…
            </p>
          )}

          {tenants !== null && tenants.length === 0 && (
            <p style={{ fontSize: '.85rem', color: 'var(--text3)', textAlign: 'center',
              lineHeight: 1.5 }}>
              There are no organisations yet.{' '}
              <Link to={PLATFORM_HOME} style={{ color: 'var(--teal)' }}>Create the first one</Link>.
            </p>
          )}

          {tenants !== null && tenants.length > 4 && (
            <div style={{ position: 'relative', marginBottom: '.7rem' }}>
              <Search size={14} style={{ position: 'absolute', left: 11, top: '50%',
                transform: 'translateY(-50%)', color: 'var(--text3)' }} />
              <input
                className="form-input"
                placeholder="Filter organisations"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                style={{ paddingLeft: 32, width: '100%' }}
                aria-label="Filter organisations"
                autoFocus
              />
            </div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: '.4rem',
            maxHeight: '48vh', overflowY: 'auto' }}>
            {visible.map((t) => {
              const active = String(t.id) === String(current);
              const s = t.stats || {};
              const people = (s.employees || 0) + (s.org_admins || 0) + (s.tenant_admins || 0);
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => choose(t)}
                  aria-current={active ? 'true' : undefined}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '.6rem',
                    padding: '.7rem .85rem', borderRadius: 10, cursor: 'pointer',
                    background: active ? 'var(--bg3)' : 'var(--bg2)',
                    border: `1px solid ${active ? 'var(--purple)' : 'var(--border)'}`,
                    color: 'var(--text)', font: 'inherit', textAlign: 'left',
                  }}
                >
                  <Building2 size={15} style={{ color: 'var(--text3)', flexShrink: 0 }} />
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span style={{ display: 'block', fontWeight: 500, overflow: 'hidden',
                      textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {t.name}
                    </span>
                    <span style={{ display: 'block', fontSize: '.72rem', color: 'var(--text3)' }}>
                      {people} {people === 1 ? 'person' : 'people'} · {s.devices || 0} device{s.devices === 1 ? '' : 's'}
                    </span>
                  </span>
                  {/* No API key here, not even the hint: choosing where to
                      work does not involve the organisation's credential. */}
                  <span style={{ fontFamily: 'var(--mono)', fontSize: '.7rem',
                    color: 'var(--text3)' }}>
                    #{t.id}
                  </span>
                  {active && <Check size={14} style={{ color: 'var(--purple)' }} />}
                </button>
              );
            })}
            {tenants !== null && tenants.length > 0 && visible.length === 0 && (
              <p style={{ fontSize: '.82rem', color: 'var(--text3)', textAlign: 'center',
                padding: '1rem 0' }}>
                Nothing matches “{filter}”.
              </p>
            )}
          </div>

          <div style={{ display: 'flex', gap: '.5rem', marginTop: '1.1rem' }}>
            <Link
              to={PLATFORM_HOME}
              className="v-btn"
              style={{ flex: 1, justifyContent: 'center', textDecoration: 'none' }}
            >
              <LayoutGrid size={13} /> All organisations
            </Link>
            <button
              type="button"
              onClick={logout}
              className="v-btn"
              style={{ flex: 1, justifyContent: 'center' }}
            >
              <LogOut size={13} /> Sign out
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
