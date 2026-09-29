// src/pages/super/ChooseOrganisation.jsx
//
// Which organisation a Super Admin is administering.
//
// A Super Admin belongs to the platform, not to a tenant — `users.tenant_id`
// is NULL for these accounts by design. Every screen under /super is
// tenant-scoped, so before the unified login there was nothing to scope them
// to and the whole area answered with
//
//     403  This admin is not attached to an organisation.
//
// on every request. This screen supplies the missing piece. The choice is sent
// as X-Acting-Tenant-Id on every /api/tenant call and re-checked server-side,
// so it is a convenience for the client rather than a grant of access.

import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertCircle, Building2, Check, LogOut, Search } from 'lucide-react';

import { useAuth } from '../../context/AuthContext';
import { superAdminApi, setActingTenant, getActingTenantId } from '../../services/api';
// .v-btn and .v-banner started life in the vault but are plain utilities; this
// screen uses them rather than growing a second set of the same rules.
import '../vault/vault.css';

export default function ChooseOrganisation() {
  const navigate = useNavigate();
  const { logout, user } = useAuth();

  const [tenants, setTenants] = useState(null);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('');

  const current = getActingTenantId();
  // Only a Super Admin can list organisations, and only they need to choose
  // one. A tenant admin reaching this URL would otherwise see a 403 for
  // something they have no business doing.
  const isSuperAdmin = user?.originalRole === 'super_admin';

  useEffect(() => {
    if (!isSuperAdmin) return undefined;
    let cancelled = false;
    superAdminApi.getTenants()
      .then((rows) => { if (!cancelled) setTenants(rows); })
      .catch((err) => {
        if (!cancelled) setError(err.message || 'Could not load organisations.');
      });
    return () => { cancelled = true; };
  }, [isSuperAdmin]);

  useEffect(() => {
    if (user && !isSuperAdmin) navigate('/super/dashboard', { replace: true });
  }, [user, isSuperAdmin, navigate]);

  if (user && !isSuperAdmin) return null;

  const choose = (tenant) => {
    setActingTenant(tenant);
    // Replace, not push: the chooser should not sit in history behind the
    // dashboard, where Back would land on it again with a selection already
    // made and no obvious reason for being there.
    navigate('/super/dashboard', { replace: true });
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
              Signed in as {user?.name || user?.email || 'Super Admin'}. Your
              account administers the platform, so pick which organisation to
              work in — you can switch at any time.
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
              There are no organisations yet. Create one with{' '}
              <code>create_organisation.py</code> on the server, then come back.
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
                autoFocus
              />
            </div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: '.4rem' }}>
            {visible.map((t) => {
              const active = String(t.id) === String(current);
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => choose(t)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '.6rem',
                    padding: '.7rem .85rem', borderRadius: 10, cursor: 'pointer',
                    background: active ? 'var(--bg3)' : 'var(--bg2)',
                    border: `1px solid ${active ? 'var(--purple)' : 'var(--border)'}`,
                    color: 'var(--text)', font: 'inherit', textAlign: 'left',
                  }}
                >
                  <Building2 size={15} style={{ color: 'var(--text3)', flexShrink: 0 }} />
                  <span style={{ flex: 1, fontWeight: 500 }}>{t.name}</span>
                  {/* The API key comes back on this endpoint but is never shown.
                      Choosing an organisation does not require seeing its
                      credential, and a list of keys on screen is a list of keys
                      in a screenshot. */}
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

          <button
            type="button"
            onClick={logout}
            className="v-btn"
            style={{ marginTop: '1.1rem', width: '100%', justifyContent: 'center' }}
          >
            <LogOut size={13} /> Sign out
          </button>
        </div>
      </div>
    </div>
  );
}
