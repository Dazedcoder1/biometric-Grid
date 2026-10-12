// src/pages/clock/TeamClock.jsx
//
// Who signed in, and when, on one day. An Org Admin sees their department;
// a Tenant Admin (or a Super Admin working in the organisation) sees
// everyone. Today's view refreshes every minute so it can stay open on a
// screen.

import React, { useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, RefreshCw } from 'lucide-react';

import DashboardLayout from '../../layouts/DashboardLayout';
import { useAuth } from '../../context/AuthContext';
import { clockApi } from '../../services/api';
import { fmtDuration, fmtTime } from '../../utils/clockFormat';
import { sidebarPropsFor } from '../../utils/sidebarRole';
import { Sessions, StatusBadge } from './MyClockLog';
import '../../components/clock.css';

const REFRESH_MS = 60_000;

const FILTERS = {
  all: () => true,
  in: (r) => r.status === 'in',
  present: (r) => r.status !== 'absent',
  absent: (r) => r.status === 'absent',
};

export default function TeamClock({ scope = 'org' }) {
  const { user } = useAuth();
  const [date, setDate] = useState('');            // '' = today
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(null);
  const [tick, setTick] = useState(0);

  const fetchDay = scope === 'tenant' ? clockApi.tenantTeam : clockApi.orgTeam;

  useEffect(() => {
    let cancelled = false;
    fetchDay(date || undefined).then(
      (d) => { if (!cancelled) { setData(d); setError(''); } },
      (err) => { if (!cancelled) setError(err.message); },
    );
    return () => { cancelled = true; };
  }, [date, tick, fetchDay]);

  // Live only while looking at today.
  useEffect(() => {
    if (date) return undefined;
    const t = setInterval(() => {
      if (document.visibilityState === 'visible') setTick((n) => n + 1);
    }, REFRESH_MS);
    return () => clearInterval(t);
  }, [date]);

  const tz = data?.timezone;
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data?.people || [])
      .filter(FILTERS[filter])
      .filter((r) => !q || r.name.toLowerCase().includes(q) || (r.employee_code || '').toLowerCase().includes(q));
  }, [data, filter, query]);

  const c = data?.counts || { people: 0, signed_in: 0, present: 0, absent: 0 };
  const title = scope === 'tenant' ? 'Sign-ins' : 'Team Sign-ins';

  return (
    <DashboardLayout title={title} {...sidebarPropsFor(user)}>
      <div className="ct-tiles">
        <button type="button" className="ct-tile" onClick={() => setFilter('all')} style={{ textAlign: 'left', cursor: 'pointer' }}>
          <span>People</span><strong>{c.people}</strong>
        </button>
        <button type="button" className="ct-tile in" onClick={() => setFilter('in')} style={{ textAlign: 'left', cursor: 'pointer' }}>
          <span>Signed in now</span><strong>{c.signed_in}</strong>
        </button>
        <button type="button" className="ct-tile" onClick={() => setFilter('present')} style={{ textAlign: 'left', cursor: 'pointer' }}>
          <span>Present</span><strong>{c.present}</strong>
        </button>
        <button type="button" className="ct-tile absent" onClick={() => setFilter('absent')} style={{ textAlign: 'left', cursor: 'pointer' }}>
          <span>Absent</span><strong>{c.absent}</strong>
        </button>
      </div>

      <div className="ct-toolbar">
        <input
          type="date"
          aria-label="Day"
          value={date || data?.date || ''}
          onChange={(e) => setDate(e.target.value)}
        />
        {date && (
          <button type="button" className="v-btn" onClick={() => setDate('')}>Today</button>
        )}
        <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Show">
          <option value="all">Everyone</option>
          <option value="in">Signed in now</option>
          <option value="present">Present</option>
          <option value="absent">Absent</option>
        </select>
        <input
          type="search"
          className="form-input"
          placeholder="Search name or code"
          aria-label="Search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          style={{ maxWidth: 240, height: 38, padding: '0 .75rem' }}
        />
        <span className="grow" />
        {!date && <span className="ct-sub">Updates every minute</span>}
        <button type="button" className="v-btn" onClick={() => setTick((n) => n + 1)}>
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      {error && <div className="wc-error" style={{ marginBottom: '1rem' }}>{error}</div>}

      <div className="ct-table-wrap">
        <table className="ct-table">
          <thead>
            <tr>
              <th aria-label="Expand" />
              <th>Name</th>
              <th>Status</th>
              <th>First in</th>
              <th>Last out</th>
              <th>Effective</th>
              <th>Gross</th>
              <th>Sessions</th>
            </tr>
          </thead>
          <tbody>
            {!data && !error && <tr><td colSpan={8} className="ct-empty">Loading…</td></tr>}
            {data && rows.length === 0 && (
              <tr><td colSpan={8} className="ct-empty">Nobody matches.</td></tr>
            )}
            {rows.map((r) => {
              const isOpen = open === r.user_id;
              const can = r.sessions.length > 0;
              return (
                <React.Fragment key={r.user_id}>
                  <tr className={can ? 'expandable' : ''} onClick={() => can && setOpen(isOpen ? null : r.user_id)}>
                    <td style={{ width: 28 }}>
                      {can && (isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />)}
                    </td>
                    <td className="strong">
                      {r.name}
                      <div className="ct-sub">
                        {r.employee_code || '—'}{r.role === 'org_admin' ? ' · Org Admin' : ''}
                      </div>
                    </td>
                    <td><StatusBadge row={r} /></td>
                    <td className="mono">{fmtTime(r.first_in, tz) || '—'}</td>
                    <td className="mono">{fmtTime(r.last_out, tz) || '—'}</td>
                    <td className="mono">{r.status === 'absent' ? '—' : fmtDuration(r.effective_seconds)}</td>
                    <td className="mono">{r.status === 'absent' ? '—' : fmtDuration(r.gross_seconds)}</td>
                    <td className="mono">{r.sessions.length || '—'}</td>
                  </tr>
                  {isOpen && (
                    <tr className="detail">
                      <td />
                      <td colSpan={7}><Sessions sessions={r.sessions} tz={tz} /></td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </DashboardLayout>
  );
}
