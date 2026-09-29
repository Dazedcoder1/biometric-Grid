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
    // Listed explicitly rather than clearing everything: localStorage is shared
    // with the theme preference and anything else the app keeps, and signing
    // out should not reset the interface.
    for (const key of [
      'access_token', 'refresh_token', 'api_key', 'auth_type', 'user',
      'token', 'userData', 'user_role', 'username', 'password',
      // The organisation a Super Admin was acting within. Left behind, the
      // next person to sign in on this machine would silently inherit it.
      'acting_tenant_id', 'acting_tenant_name',
    ]) {
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
