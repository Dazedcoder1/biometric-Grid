// src/services/apiBase.js
//
// Where the API lives. VITE_API_BASE_URL is baked into the bundle at build
// time, so a server built with a developer's .env (VITE_API_BASE_URL=
// http://localhost:8000) ships a site that sends every request — sign-in
// included — to the VISITOR's own machine: net::ERR_CONNECTION_REFUSED.
//
// So a localhost API is only honoured when the page itself is on localhost.
// Anywhere else it falls back to the production API.

export const PRODUCTION_API = 'https://api-work.gridsphere.in';

const LOCAL_HOSTS = /^(localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0)$/i;

export function resolveApiBase(configured, pageHost) {
  const value = (configured || '').trim().replace(/\/+$/, '');
  if (!value) return PRODUCTION_API;

  let apiHost;
  try {
    apiHost = new URL(value).hostname;
  } catch {
    return PRODUCTION_API; // not a URL at all
  }

  const pageIsLocal = !pageHost || LOCAL_HOSTS.test(pageHost);
  if (LOCAL_HOSTS.test(apiHost) && !pageIsLocal) return PRODUCTION_API;
  return value;
}

export const API_BASE_URL = resolveApiBase(
  import.meta.env.VITE_API_BASE_URL,
  typeof window !== 'undefined' ? window.location.hostname : '',
);
