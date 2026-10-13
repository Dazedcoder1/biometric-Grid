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
//
// The HR portal (/hr/login) is the same form with one difference: it only lets
// in accounts that can run payroll — someone given HR access, or a Tenant
// Admin or Super Admin — and lands them on payroll instead of their own
// dashboard. Anyone else is told so and signed straight back out.

import React, { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  ArrowRight, Briefcase, Eye, EyeOff, Lock, Moon, ShieldCheck, Sun, User,
} from 'lucide-react';

import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { authApi } from '../services/api';
import { HR_HOME, homePathForUser, isSuperAdmin, setPortal } from '../utils/roles';

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
function destinationFor(user, from) {
  const home = homePathForUser(user);
  if (typeof from !== 'string') return home;
  // Must be a single-slash absolute path: "//evil.com" and "https://evil.com"
  // are both rejected here.
  if (!/^\/[^/]/.test(from)) return home;

  const section = (path) => path.split('/')[1];
  // A Super Admin works across the platform screens and, once an organisation
  // is chosen, the tenant screens — but has no vault (see ProtectedRoute).
  const allowed = isSuperAdmin(user)
    ? ['platform', 'super', 'choose-organisation', 'payroll']
    : [section(home), 'vault', 'my-pay', 'my-documents', 'emp', 'org',
       ...(user?.isHr ? ['payroll', 'documents'] : [])];
  return allowed.includes(section(from)) ? from : home;
}

/** Can this account use the HR portal? HR access, or an admin who has payroll anyway. */
function canUseHr(user) {
  return !!user && (user.isHr || user.role === 'tenant_admin');
}

export default function Login({ portal = 'main' }) {
  const hr = portal === 'hr';
  const navigate = useNavigate();
  const location = useLocation();
  const { login, logout, user, loading } = useAuth();
  const { theme, toggleTheme } = useTheme();

  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [forgot, setForgot] = useState(false);
  const [forgotSent, setForgotSent] = useState('');
  // Sent here because the session could not be renewed (services/session.js),
  // with the page they were on so signing in returns them to it.
  const params = new URLSearchParams(location.search);
  const expired = params.get('expired') === '1';
  const returnTo = location.state?.from || params.get('from');

  // Already signed in — go where this person belongs rather than showing them
  // a form they do not need.
  useEffect(() => {
    if (!loading && user) {
      if (hr && canUseHr(user) && !user.mustChangePassword) {
        setPortal('hr');
        navigate(HR_HOME, { replace: true });
        return;
      }
      navigate(user.mustChangePassword ? '/change-password' : homePathForUser(user), { replace: true });
    }
  }, [user, loading, navigate, hr]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');

    try {
      const res = await authApi.login(identifier.trim(), password);
      const signedIn = login(res.access_token, { refreshToken: res.refresh_token });

      if (hr) {
        if (!canUseHr(signedIn)) {
          logout();
          setError("This account doesn't have HR access. Ask your Tenant Admin, or use the main sign-in.");
          setPassword('');
          return;
        }
        setPortal('hr');
        navigate(signedIn.mustChangePassword ? '/change-password'
          : (returnTo ? destinationFor(signedIn, returnTo) : HR_HOME), { replace: true });
        return;
      }
      setPortal('main');
      navigate(
        signedIn.mustChangePassword
          ? '/change-password'
          : destinationFor(signedIn, returnTo),
        { replace: true },
      );
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
              style={hr
                ? { background: 'rgba(168,85,247,0.14)', color: 'var(--purple)' }
                : { background: 'rgba(0,212,170,0.12)', color: 'var(--teal)' }}
            >
              {hr ? <Briefcase size={30} /> : <ShieldCheck size={32} />}
            </div>
            <h2 className="login-title">{hr ? 'HR Portal' : 'The Sentinel'}</h2>
            <p className="login-subtitle">
              {hr ? 'Payroll, salaries and expense claims' : 'Biometric Orchestration Platform'}
            </p>
          </div>

          {expired && !error && (
            <div role="status" style={{
              background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.3)', borderRadius: 8,
              padding: '0.75rem', marginBottom: '1rem', color: 'var(--warn)', fontSize: '0.85rem', textAlign: 'center',
            }}>
              Your session has ended. Sign in again to continue where you left off.
            </div>
          )}

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

          {forgot ? (
            <form className="login-form" onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true); setError('');
              try {
                const r = await authApi.forgotPassword(identifier.trim());
                setForgotSent(r.message);
              } catch (err) {
                setError(err.message || 'Could not send the request. Try again.');
              } finally {
                setBusy(false);
              }
            }}>
              <p style={{ fontSize: '.85rem', color: 'var(--text2)', margin: 0 }}>
                Enter your email or employee ID. Your Department Admin and Organisation Admin are asked to
                reset your password; they will give you a temporary one, and you choose your own when you sign in.
              </p>
              {forgotSent ? (
                <div role="status" style={{ background: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.3)', borderRadius: 8, padding: '0.75rem', color: 'var(--ok)', fontSize: '0.85rem' }}>
                  {forgotSent}
                </div>
              ) : (
                <>
                  <div className="form-group">
                    <label className="form-label" htmlFor="forgot-id">Email or employee ID</label>
                    <div className="input-wrap">
                      <User className="input-icon" size={18} />
                      <input id="forgot-id" type="text" className="form-input" required autoFocus
                        value={identifier} onChange={(e) => setIdentifier(e.target.value)} />
                    </div>
                  </div>
                  <button type="submit" className="login-btn" disabled={busy}
                    style={hr ? { background: 'var(--purple)', color: '#fff' } : { background: 'var(--teal)', color: 'var(--on-teal)' }}>
                    {busy ? 'Sending…' : 'Ask for a reset'}
                  </button>
                </>
              )}
              <button type="button" onClick={() => { setForgot(false); setForgotSent(''); setError(''); }}
                style={{ background: 'none', border: 'none', color: 'var(--teal)', cursor: 'pointer', fontSize: '.85rem' }}>
                Back to sign in
              </button>
            </form>
          ) : (
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
              style={hr
                ? { background: 'var(--purple)', color: '#fff' }
                : { background: 'var(--teal)', color: 'var(--on-teal)' }}
              disabled={busy}
            >
              {busy ? 'Signing in…' : <>{hr ? 'Sign in to HR' : 'Sign in'} <ArrowRight size={18} /></>}
            </button>
            <button type="button" onClick={() => { setForgot(true); setError(''); }}
              style={{ background: 'none', border: 'none', color: 'var(--text3)', cursor: 'pointer', fontSize: '.82rem', alignSelf: 'center' }}>
              Forgot password?
            </button>
          </form>
          )}

          <div className="login-footer">
            {hr ? (
              <p>
                For people with HR access. Not HR? <Link to="/login">Use the main sign-in</Link>.
              </p>
            ) : (
              <p>
                Your access level is set by your account — there is nothing to
                choose here. All actions are recorded in the audit log.
                {' '}HR team? <Link to="/hr/login">Sign in to the HR portal</Link>.
              </p>
            )}
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
