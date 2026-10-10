// src/pages/ChangePasswordRequired.jsx
//
// Where someone lands after an administrator gives them a temporary password.
//
// The server refuses every other request until a new password is chosen
// (dependencies.get_current_user), so this screen stands alone — no sidebar,
// no dashboard to fail behind it. Changing the password returns fresh tokens,
// which replace the ones that still say "must change", and every other
// session on the account is signed out.

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertCircle, Check, Eye, EyeOff, KeyRound, LogOut } from 'lucide-react';

import { useAuth } from '../context/AuthContext';
import { authApi } from '../services/api';
import { homePathForUser } from '../utils/roles';
import './vault/vault.css';

// Mirrors the server's rule (routes/auth ChangePasswordRequest).
const RULES = [
  { test: (p) => p.length >= 8, label: 'At least 8 characters' },
  { test: (p) => /[A-Z]/.test(p), label: 'An uppercase letter' },
  { test: (p) => /[a-z]/.test(p), label: 'A lowercase letter' },
  { test: (p) => /[0-9]/.test(p), label: 'A number' },
];

export default function ChangePasswordRequired() {
  const navigate = useNavigate();
  const { user, login, logout } = useAuth();

  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const ruleResults = RULES.map((r) => ({ ...r, ok: r.test(next) }));
  const policyOk = ruleResults.every((r) => r.ok);
  const matches = next.length > 0 && next === confirm;
  const different = next.length > 0 && next !== current;
  const ready = current && policyOk && matches && different;

  const submit = async (e) => {
    e.preventDefault();
    if (!ready) return;
    setBusy(true);
    setError('');
    try {
      const res = await authApi.changePassword({ old_password: current, new_password: next });
      // The response carries tokens without the "must change" flag.
      const signedIn = login(res.access_token, { refreshToken: res.refresh_token });
      navigate(homePathForUser(signedIn), { replace: true });
    } catch (err) {
      setError(
        err.status === 401
          ? 'The current password is not right. Use the temporary password your administrator gave you.'
          : (err.message || 'Your password could not be changed.'),
      );
    } finally {
      setBusy(false);
    }
  };

  const field = (id, label, value, onChange, autoComplete) => (
    <div className="form-group">
      <label className="form-label" htmlFor={id}>{label}</label>
      <input
        id={id}
        type={show ? 'text' : 'password'}
        className="form-input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoComplete={autoComplete}
        style={{ width: '100%', fontFamily: show ? 'var(--mono)' : undefined }}
      />
    </div>
  );

  return (
    <div className="login-page">
      <div className="grid-bg" />
      <div className="login-container" style={{ maxWidth: 460 }}>
        <div className="login-card">
          <div className="login-header">
            <div
              className="login-logo-circle"
              style={{ background: 'rgba(245,158,11,0.12)', color: 'var(--warn)' }}
            >
              <KeyRound size={30} />
            </div>
            <h2 className="login-title">Choose a new password</h2>
            <p className="login-subtitle">
              {user?.name ? `${user.name}, your` : 'Your'} password was reset by an
              administrator. Pick your own before continuing — it signs you out
              everywhere else.
            </p>
          </div>

          {error && (
            <div className="v-banner bad" role="alert">
              <AlertCircle size={14} /><span>{error}</span>
            </div>
          )}

          <form onSubmit={submit} noValidate>
            {field('cp-current', 'Temporary password', current, setCurrent, 'current-password')}
            {field('cp-new', 'New password', next, setNext, 'new-password')}
            {field('cp-confirm', 'Repeat new password', confirm, setConfirm, 'new-password')}

            <button
              type="button"
              className="v-btn"
              onClick={() => setShow((s) => !s)}
              style={{ marginBottom: '.8rem' }}
            >
              {show ? <EyeOff size={13} /> : <Eye size={13} />} {show ? 'Hide' : 'Show'} passwords
            </button>

            <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 .4rem', fontSize: '.8rem' }}>
              {ruleResults.map((r) => (
                <li key={r.label} style={{ color: r.ok ? 'var(--ok)' : 'var(--text3)', display: 'flex', gap: 6, alignItems: 'center' }}>
                  <Check size={12} style={{ opacity: r.ok ? 1 : 0.3 }} /> {r.label}
                </li>
              ))}
              <li style={{ color: matches ? 'var(--ok)' : 'var(--text3)', display: 'flex', gap: 6, alignItems: 'center' }}>
                <Check size={12} style={{ opacity: matches ? 1 : 0.3 }} /> Both new passwords match
              </li>
              <li style={{ color: different ? 'var(--ok)' : 'var(--text3)', display: 'flex', gap: 6, alignItems: 'center' }}>
                <Check size={12} style={{ opacity: different ? 1 : 0.3 }} /> Different from the temporary one
              </li>
            </ul>

            <button type="submit" className="v-btn-primary" disabled={!ready || busy}>
              {busy ? 'Saving…' : 'Save and continue'}
            </button>
          </form>

          <p style={{ fontSize: '.78rem', color: 'var(--text3)', textAlign: 'center', margin: '1rem 0 .5rem', lineHeight: 1.5 }}>
            Don&apos;t have the temporary password? Ask the administrator who reset it.
          </p>
          <button
            type="button"
            className="v-btn"
            onClick={logout}
            style={{ width: '100%', justifyContent: 'center' }}
          >
            <LogOut size={13} /> Sign out
          </button>
        </div>
      </div>
    </div>
  );
}
