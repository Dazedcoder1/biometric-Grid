// src/services/session.js
//
// Keeping a signed-in session alive.
//
// Access tokens are short-lived (ACCESS_TOKEN_EXPIRE_MINUTES on the server,
// 60 by default). Before this, nothing renewed them: an hour after signing in
// every request came back 401 and each screen showed "Invalid or expired
// token" until the person signed in again.
//
// Now:
//   * the token is renewed in the background shortly before it expires
//     (scheduleRenewal, started by AuthContext), and again whenever the tab
//     comes back into view after the computer slept;
//   * any request that still gets a 401 is renewed and retried once
//     (authorizedFetch, used by every API call);
//   * only when renewal itself is refused — the refresh token expired, was
//     revoked, or the account was deactivated — is the person sent to sign in,
//     and then back to the page they were on.
//
// Several tabs share one localStorage. Renewal takes a cross-tab lock
// (navigator.locks) and re-reads storage inside it, so two tabs never spend
// the same single-use refresh token: the second one finds the first one's new
// token already there and uses it.

import { API_BASE_URL } from './apiBase';

const ACCESS = 'access_token';
const REFRESH = 'refresh_token';
const RENEW_EARLY_MS = 2 * 60 * 1000;      // renew two minutes before expiry
const LOCK_NAME = 'sentinel-session-renewal';

/** Fired on window when the session is renewed ({ token }) or ended ({ ended: true }). */
export const SESSION_EVENT = 'sentinel:session';

/** Everything a signed-in session keeps in localStorage. */
export const SESSION_KEYS = [
  'access_token', 'refresh_token', 'api_key', 'auth_type', 'user',
  'token', 'userData', 'user_role', 'username', 'password',
  'acting_tenant_id', 'acting_tenant_name', 'portal',
];

function read(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}

/** The token's expiry in ms since the epoch, or null if it cannot be read. */
export function tokenExpiry(token) {
  try {
    const b64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const { exp } = JSON.parse(atob(b64));
    return typeof exp === 'number' ? exp * 1000 : null;
  } catch {
    return null;
  }
}

/** Valid for at least `marginMs` more. */
export function isFresh(token, marginMs = 30_000) {
  const exp = token ? tokenExpiry(token) : null;
  return !!exp && exp - Date.now() > marginMs;
}

export class SessionEndedError extends Error {
  constructor(message = 'Your session has ended. Please sign in again.') {
    super(message);
    this.name = 'SessionEndedError';
    this.sessionEnded = true;
  }
}

function withLock(fn) {
  if (typeof navigator !== 'undefined' && navigator.locks?.request) {
    return navigator.locks.request(LOCK_NAME, fn);
  }
  return fn();
}

/**
 * Sign-out because the session cannot be renewed. Clears the stored session
 * and goes to the sign-in page the person came through, remembering where
 * they were so signing in brings them back.
 */
export function endSession() {
  const portal = read('portal');
  for (const key of SESSION_KEYS) {
    try { localStorage.removeItem(key); } catch { /* ignore */ }
  }
  window.dispatchEvent(new CustomEvent(SESSION_EVENT, { detail: { ended: true } }));
  const here = window.location.pathname + window.location.search;
  if (/^\/(hr\/)?login/.test(window.location.pathname)) return;
  const page = portal === 'hr' ? '/hr/login' : '/login';
  window.location.assign(`${page}?expired=1&from=${encodeURIComponent(here)}`);
}

let inflight = null;

/**
 * A fresh access token. `staleToken` is the one that just failed (or is about
 * to expire); if storage already holds a newer, valid one — renewed by
 * another tab or an earlier call — that is returned without asking the server.
 */
export function renewSession(staleToken) {
  if (inflight) return inflight;
  inflight = withLock(async () => {
    const current = read(ACCESS);
    if (current && current !== staleToken && isFresh(current)) return current;

    const refresh = read(REFRESH);
    if (!refresh) {
      endSession();
      throw new SessionEndedError();
    }

    let res;
    try {
      res = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
      });
    } catch {
      // Offline or the server is restarting: not a reason to sign anyone
      // out. The caller sees an ordinary error and can retry.
      throw new Error('Could not reach the server to renew your session. Check your connection.');
    }

    if (res.status === 401 || res.status === 403) {
      // One last look: another tab may have renewed while this request was
      // in flight on a browser without navigator.locks.
      const again = read(ACCESS);
      if (again && again !== current && isFresh(again)) return again;
      endSession();
      throw new SessionEndedError();
    }
    if (!res.ok) throw new Error(`Could not renew your session (${res.status}). Please try again.`);

    const data = await res.json();
    try {
      localStorage.setItem(ACCESS, data.access_token);
      if (data.refresh_token) localStorage.setItem(REFRESH, data.refresh_token);
    } catch { /* storage full or blocked: the token still works for this tab */ }
    window.dispatchEvent(new CustomEvent(SESSION_EVENT, { detail: { token: data.access_token } }));
    return data.access_token;
  }).finally(() => { inflight = null; });
  return inflight;
}

function bearerOf(headers) {
  if (!headers) return null;
  const value = headers.Authorization || headers.authorization;
  return typeof value === 'string' && value.startsWith('Bearer ') ? value.slice(7) : null;
}

/**
 * fetch, but a 401 caused by an expired access token is renewed and retried
 * once. Requests made with an API key, the sign-in calls themselves, and a
 * vault "confirm it's you" 401 are returned as they are.
 */
export async function authorizedFetch(url, init = {}) {
  const res = await fetch(url, init);
  if (res.status !== 401) return res;
  const used = bearerOf(init.headers);
  if (!used) return res;
  if (/\/api\/auth\/(login|refresh|tenant-login)/.test(url)) return res;
  if (res.headers.get('X-Step-Up-Required')) return res;

  let fresh;
  try {
    fresh = await renewSession(used);
  } catch {
    return res;
  }
  return fetch(url, { ...init, headers: { ...init.headers, Authorization: `Bearer ${fresh}` } });
}

/**
 * Renew in the background before the token runs out, and when the tab comes
 * back after sleep. Returns a function that stops it.
 */
export function scheduleRenewal(token) {
  if (!token) return () => {};
  const exp = tokenExpiry(token);
  if (!exp) return () => {};

  const renew = () => { renewSession(token).catch(() => { /* handled inside */ }); };
  const wait = Math.max(0, exp - Date.now() - RENEW_EARLY_MS);
  // setTimeout caps at ~24.8 days; a token that long-lived needs no timer.
  const timer = wait < 2_000_000_000 ? setTimeout(renew, wait) : null;

  const onWake = () => {
    if (document.visibilityState === 'visible' && !isFresh(read(ACCESS) || token, RENEW_EARLY_MS)) renew();
  };
  document.addEventListener('visibilitychange', onWake);
  window.addEventListener('focus', onWake);
  return () => {
    if (timer) clearTimeout(timer);
    document.removeEventListener('visibilitychange', onWake);
    window.removeEventListener('focus', onWake);
  };
}
