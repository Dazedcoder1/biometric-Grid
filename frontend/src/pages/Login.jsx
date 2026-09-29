// src/pages/Login.jsx
//
// One sign-in form for everyone.
//
// There used to be three, behind a gateway that asked you to pick Tenant
// Admin, Org Admin or Employee first. That question was never the app's to
// ask: the server decides what you are from your credentials, and the three
// forms posted to the same endpoint with the same two fields. All the picker
// did was let you choose wrong — and because each page assigned its own role
// to the session, choosing wrong left the app showing you a dashboard you had
// no access to until the next reload corrected it.
//
// Now: one form, and the role comes from the token the server returns.

import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  ArrowRight, Eye, EyeOff, Lock, Moon, ShieldCheck, Sun, User,
} from 'lucide-react';

import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { authApi } from '../services/api';
import { homePathFor } from '../utils/roles';

/**
 * Where to land after a successful sign-in.
 *
 * Prefers the page they were trying to reach when they were bounced here, but
 * only when their role could actually open it — sending an employee back to
 * /super/devices means ProtectedRoute redirects them again the moment they
 * arrive, which reads as the sign-in having failed. Anything that is not a
 * plain in-app path is ignored outright, so a crafted `from` cannot turn this
 * into an open redirect.
 */
function destinationFor(role, from) {
  const home = homePathFor(role);
  if (typeof from !== 'string') return home;
  // Must be a single-slash absolute path: "//evil.com" and "https://evil.com"
  // are both rejected here.
  if (!/^\/[^/]/.test(from)) return home;

  const section = (path) => path.split('/')[1];
  return section(from) === section(home) || section(from) === 'vault' ? from : home;
}

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, user, loading } = useAuth();
  const { theme, toggleTheme } = useTheme();

  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  // Already signed in — go where this person belongs rather than showing them
  // a form they do not need.
  useEffect(() => {
    if (!loading && user) navigate(homePathFor(user.role), { replace: true });
  }, [user, loading, navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');

    try {
      const res = await authApi.login(identifier.trim(), password);
      const signedIn = login(res.access_token, { refreshToken: res.refresh_token });

      navigate(destinationFor(signedIn.role, location.state?.from), { replace: true });
    } catch (err) {
      // The server does not say which half was wrong, and neither do we: an
      // error that distinguishes "no such user" from "wrong password" confirms
      // which accounts exist to anyone who asks.
      setError(err.message || 'Those details were not accepted.');
      setPassword('');
    } finally {
      setBusy(false);
    }
  };

  if (loading) return null;

  return (
    <div className="login-page">
      <div className="grid-bg" />

      <div style={{ position: 'absolute', top: 20, right: 20, zIndex: 50 }}>
        <button
          type="button"
          className="tb-action-icon theme-toggle"
          onClick={toggleTheme}
          aria-label="Toggle light and dark mode"
        >
          {theme === 'dark' ? <Sun size={22} /> : <Moon size={22} />}
        </button>
      </div>

      <div className="login-container">
        <div className="login-card">
          <div className="login-header">
            <div
              className="login-logo-circle"
              style={{ background: 'rgba(0,212,170,0.12)', color: 'var(--teal)' }}
            >
              <ShieldCheck size={32} />
            </div>
            <h2 className="login-title">The Sentinel</h2>
            <p className="login-subtitle">Biometric Orchestration Platform</p>
          </div>

          {error && (
            <div
              role="alert"
              style={{
                background: 'rgba(239,68,68,0.1)',
                border: '1px solid rgba(239,68,68,0.3)',
                borderRadius: 8,
                padding: '0.75rem',
                marginBottom: '1rem',
                color: 'var(--bad)',
                fontSize: '0.85rem',
                textAlign: 'center',
              }}
            >
              {error}
            </div>
          )}

          <form className="login-form" onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label" htmlFor="identifier">
                Email or employee ID
              </label>
              <div className="input-wrap">
                <User className="input-icon" size={18} />
                <input
                  id="identifier"
                  name="username"
                  type="text"
                  className="form-input"
                  placeholder="you@company.com"
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  required
                  autoFocus
                  autoComplete="username"
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="password">Password</label>
              <div className="input-wrap">
                <Lock className="input-icon" size={18} />
                <input
                  id="password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  className="form-input"
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  className="password-toggle"
                  onClick={() => setShowPassword((s) => !s)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              className={`login-btn ${busy ? 'loading' : ''}`}
              style={{ background: 'var(--teal)', color: 'var(--on-teal)' }}
              disabled={busy}
            >
              {busy ? 'Signing in…' : <>Sign in <ArrowRight size={18} /></>}
            </button>
          </form>

          <div className="login-footer">
            <p>
              Your access level is set by your account — there is nothing to
              choose here. All actions are recorded in the audit log.
            </p>
          </div>
        </div>

        <div className="login-status-badges">
          <div className="status-badge"><div className="dot" /> System online</div>
          <div className="status-badge">
            <div className="dot" style={{ background: 'var(--blue)' }} /> AES-256 encrypted
          </div>
        </div>
      </div>
    </div>
  );
}
