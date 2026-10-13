// src/context/AuthContext.jsx
//
// Who is signed in, derived from the access token and nothing else.
//
// The important change from the earlier version: `login()` no longer accepts a
// user object from its caller. The three role-specific login pages each passed
// the role belonging to the page you happened to click, so the app's idea of
// your role came from a URL until the next reload, when the token decoder
// quietly replaced it with the real one. Now there is one source — the token —
// and one function that reads it.

import React, { createContext, useContext, useEffect, useState } from 'react';
import { userFromToken } from '../utils/roles';
import { SESSION_EVENT, SESSION_KEYS, scheduleRenewal } from '../services/session';

const AuthContext = createContext();

// The legacy tenant API key. It carries a tenant, not a person, so there is no
// user id and no name to show — which is exactly why password logins exist for
// all three roles now. Kept working so existing machine-to-machine setups and
// anyone mid-migration are not locked out.
const API_KEY_USER = {
  id: null,
  role: 'tenant_admin',
  originalRole: 'tenant_admin',
  name: 'Tenant Admin',
  email: null,
  viaApiKey: true,
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem('access_token'));
  const [authType, setAuthType] = useState(() => localStorage.getItem('auth_type'));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (authType === 'api_key') {
      if (localStorage.getItem('api_key')) setUser(API_KEY_USER);
      else performLogout();
    } else if (token) {
      const derived = userFromToken(token);
      // A token we cannot read, or one carrying a role this app has no screens
      // for, is not a session. Signing out is the honest response: the
      // alternative is a shell with no working navigation.
      if (derived) setUser(derived);
      else performLogout();
    } else {
      setUser(null);
    }
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, authType]);

  // Keep the session alive: renew the access token shortly before it expires
  // and whenever the tab wakes up (services/session.js). API-key sessions
  // have nothing to renew.
  useEffect(() => {
    if (authType === 'api_key' || !token) return undefined;
    return scheduleRenewal(token);
  }, [token, authType]);

  // A renewal (in this tab or another) or a session that could not be
  // renewed. The new token re-derives the user, so a role or HR change made
  // by an admin shows up at the next renewal without signing in again.
  useEffect(() => {
    const onSession = (e) => {
      if (e.detail?.ended) {
        setToken(null);
        setUser(null);
      } else if (e.detail?.token) {
        setToken(e.detail.token);
      }
    };
    const onStorage = (e) => {
      if (e.key !== 'access_token') return;
      if (e.newValue) setToken(e.newValue);
      else if (localStorage.getItem('auth_type') !== 'api_key') { setToken(null); setUser(null); }
    };
    window.addEventListener(SESSION_EVENT, onSession);
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener(SESSION_EVENT, onSession);
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  /**
   * Start a session from an access token.
   *
   * Takes the token alone on purpose. Anything the UI needs about the person
   * comes out of it, so there is no way for a caller to assert a role.
   */
  const login = (accessToken, { refreshToken } = {}) => {
    const derived = userFromToken(accessToken);
    if (!derived) throw new Error('The server returned a sign-in token this app cannot read.');

    localStorage.setItem('access_token', accessToken);
    localStorage.setItem('auth_type', 'bearer');
    if (refreshToken) localStorage.setItem('refresh_token', refreshToken);

    setToken(accessToken);
    setAuthType('bearer');
    setUser(derived);
    return derived;
  };

  /** Sign in with a tenant API key. No token, no identity — see API_KEY_USER. */
  const loginWithApiKey = (apiKey) => {
    localStorage.setItem('api_key', apiKey);
    localStorage.setItem('auth_type', 'api_key');
    setAuthType('api_key');
    setUser(API_KEY_USER);
    return API_KEY_USER;
  };

  const performLogout = () => {
    // The next person at this browser starts from the main sign-in.
    try { localStorage.removeItem('portal'); } catch { /* ignore */ }
    // Listed explicitly rather than clearing everything: localStorage is shared
    // with the theme preference and anything else the app keeps, and signing
    // out should not reset the interface.
    // SESSION_KEYS includes the organisation a Super Admin was acting
    // within: left behind, the next person to sign in on this machine would
    // silently inherit it.
    for (const key of SESSION_KEYS) {
      localStorage.removeItem(key);
    }

    setToken(null);
    setAuthType(null);
    setUser(null);
  };

  const logout = () => {
    performLogout();
    // A hard navigation, not a route change: it drops every component's state,
    // including any credential secret still held in memory on the vault screen.
    window.location.href = '/';
  };

  const hasRole = (allowedRoles) => !!user && allowedRoles.includes(user.role);

  return (
    <AuthContext.Provider
      value={{ user, token, authType, login, loginWithApiKey, logout, loading, hasRole }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
