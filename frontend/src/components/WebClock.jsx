// src/components/WebClock.jsx
//
// Sign In / Sign Out from the browser, in the style of an HR web clock: a
// live clock, one big button, and a running count of today's hours.
//
// The server owns the state. The timer only interpolates between fetches —
// it adds the seconds since the last answer while signed in — and the card
// re-reads the server every two minutes, so a punch made at a fingerprint
// scanner shows up here without a reload.

import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Fingerprint, Globe, LogIn, LogOut, Timer } from 'lucide-react';

import { clockApi, commonApi } from '../services/api';
import {
  SOURCE_LABEL, fmtDuration, fmtTime, fmtTimer, wallClock,
} from '../utils/clockFormat';
import './clock.css';

const REFRESH_MS = 120_000;

function SourceIcon({ source }) {
  const Icon = source === 'web' ? Globe : Fingerprint;
  return <Icon size={11} aria-label={SOURCE_LABEL[source] || source} />;
}

export default function WebClock({ historyPath }) {
  const [day, setDay] = useState(null);
  const [fetchedAt, setFetchedAt] = useState(0);
  const [now, setNow] = useState(0);
  const [minHours, setMinHours] = useState(9);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const accept = useCallback((d) => {
    setDay(d);
    setFetchedAt(Date.now());
  }, []);

  useEffect(() => {
    let cancelled = false;
    const read = () => clockApi.today().then(
      (d) => { if (!cancelled) { accept(d); setError(''); } },
      (err) => { if (!cancelled) setError(err.message); },
    );
    read();
    commonApi.getSettings().then(
      (s) => { if (!cancelled && s?.min_working_hours) setMinHours(Number(s.min_working_hours)); },
      () => {},
    );
    const poll = setInterval(() => { if (document.visibilityState === 'visible') read(); }, REFRESH_MS);
    return () => { cancelled = true; clearInterval(poll); };
  }, [accept]);

  // The ticking second hand.
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const signedIn = day?.status === 'in';
  const tz = day?.timezone;

  const punch = async () => {
    setBusy(true);
    setError('');
    try {
      accept(signedIn ? await clockApi.signOut() : await clockApi.signIn());
    } catch (err) {
      setError(err.message);
      // Most likely signed in or out somewhere else (another tab, a scanner).
      // Show the real state rather than leave a button that will fail again.
      clockApi.today().then(accept, () => {});
    } finally {
      setBusy(false);
    }
  };

  const clockMs = now || fetchedAt || 0;
  const live = signedIn && now && fetchedAt ? Math.max(0, (now - fetchedAt) / 1000) : 0;
  const effective = (day?.effective_seconds || 0) + live;
  const gross = (day?.gross_seconds || 0) + live;
  const target = minHours * 3600;
  const pct = target ? Math.min(100, (effective / target) * 100) : 0;
  const wall = clockMs ? wallClock(clockMs, tz) : null;

  let status = 'Loading…';
  if (day) {
    if (signedIn) status = `Signed in since ${fmtTime(day.signed_in_since, tz)}`;
    else if (day.status === 'out') status = `Signed out at ${fmtTime(day.last_out, tz)}`;
    else status = 'You have not signed in today';
  }

  return (
    <section className={`wc ${signedIn ? 'is-in' : ''}`} aria-label="Sign-in clock">
      <div className="wc-top">
        <div>
          <div className="wc-label">{wall ? wall.date : 'Today'}</div>
          <div className="wc-clock" aria-live="off">
            {wall ? wall.time : '--:--:--'}<small>{wall?.ampm}</small>
          </div>
          <div className="wc-status"><span className="dot" />{status}</div>
        </div>

        <button
          type="button"
          className={`wc-btn ${signedIn ? 'out' : 'in'}`}
          onClick={punch}
          disabled={busy || !day}
        >
          {signedIn ? <LogOut size={18} /> : <LogIn size={18} />}
          {busy ? 'Please wait…' : signedIn ? 'Sign Out' : 'Sign In'}
        </button>
      </div>

      <div className="wc-stats">
        <div className="wc-stat primary">
          <span>Effective hours</span>
          <strong>{fmtTimer(effective)}</strong>
        </div>
        <div className="wc-stat">
          <span>Gross hours</span>
          <strong>{fmtTimer(gross)}</strong>
        </div>
        <div className="wc-stat">
          <span>First in</span>
          <strong>{day?.first_in ? fmtTime(day.first_in, tz) : '—'}</strong>
        </div>
        <div className="wc-stat">
          <span>Last out</span>
          <strong>{day?.last_out ? fmtTime(day.last_out, tz) : '—'}</strong>
        </div>
      </div>

      <div className="wc-progress" title={`Minimum day: ${minHours} hours`}>
        <div className="wc-progress-bar">
          <div className={`wc-progress-fill ${pct >= 100 ? 'done' : ''}`} style={{ width: `${pct}%` }} />
        </div>
        <div className="wc-progress-text">
          <span>{fmtDuration(effective)} of {minHours}h</span>
          <span>
            {pct >= 100 ? 'Minimum day complete' : `${fmtDuration(Math.max(0, target - effective))} to go`}
          </span>
        </div>
      </div>

      {day?.sessions?.length > 0 && (
        <div className="wc-sessions" aria-label="Today's sessions">
          {day.sessions.map((s) => (
            <span key={s.in} className={`wc-session ${s.out ? '' : 'open'}`}>
              <SourceIcon source={s.in_source} />
              {fmtTime(s.in, tz)}
              {' → '}
              {s.out ? (
                <>
                  {fmtTime(s.out, tz)}
                  <SourceIcon source={s.out_source} />
                </>
              ) : 'now'}
            </span>
          ))}
        </div>
      )}

      {error && <div className="wc-error" role="alert">{error}</div>}

      <div className="wc-foot">
        <span>
          <Globe size={11} /> web · <Fingerprint size={11} /> scanner — both count towards the same day.
        </span>
        {historyPath && (
          <Link to={historyPath}><Timer size={12} /> View sign-in log</Link>
        )}
      </div>
    </section>
  );
}
