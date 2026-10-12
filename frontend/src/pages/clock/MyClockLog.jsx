// src/pages/clock/MyClockLog.jsx
//
// My sign-in log: the clock card, then one row per day for the last 7, 30 or
// 90 days. A row opens to show that day's individual sessions and whether
// each punch came from the web or a scanner.

import React, { useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, Fingerprint, Globe } from 'lucide-react';

import DashboardLayout from '../../layouts/DashboardLayout';
import WebClock from '../../components/WebClock';
import { useAuth } from '../../context/AuthContext';
import { clockApi } from '../../services/api';
import { fmtDay, fmtDuration, fmtTime } from '../../utils/clockFormat';
import { sidebarPropsFor } from '../../utils/sidebarRole';
import '../../components/clock.css';

export function StatusBadge({ row }) {
  if (row.status === 'in') return <span className="ct-badge in"><span className="dot" />Signed in</span>;
  if (row.unclosed) return <span className="ct-badge warn" title="Signed in but never signed out">No sign-out</span>;
  if (row.status === 'out') return <span className="ct-badge out">Present</span>;
  return <span className="ct-badge absent">Absent</span>;
}

export function Sessions({ sessions, tz }) {
  if (!sessions?.length) return <span className="ct-sub">No punches.</span>;
  return (
    <div className="wc-sessions" style={{ marginTop: '.2rem' }}>
      {sessions.map((s) => {
        const InIcon = s.in_source === 'web' ? Globe : Fingerprint;
        const OutIcon = s.out_source === 'web' ? Globe : Fingerprint;
        return (
          <span key={s.in} className={`wc-session ${s.out ? '' : 'open'}`}>
            <InIcon size={11} /> {fmtTime(s.in, tz)} → {s.out ? <>{fmtTime(s.out, tz)} <OutIcon size={11} /></> : '…'}
          </span>
        );
      })}
    </div>
  );
}

export default function MyClockLog() {
  const { user } = useAuth();
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(null);

  useEffect(() => {
    let cancelled = false;
    clockApi.history(days).then(
      (d) => { if (!cancelled) { setData(d); setError(''); } },
      (err) => { if (!cancelled) setError(err.message); },
    );
    return () => { cancelled = true; };
  }, [days]);

  const rows = data?.days || [];
  const tz = data?.timezone;
  const present = rows.filter((r) => r.status !== 'absent').length;
  const total = rows.reduce((n, r) => n + r.effective_seconds, 0);

  return (
    <DashboardLayout title="My Sign-in Log" {...sidebarPropsFor(user)}>
      <WebClock />

      <div className="ct-toolbar">
        <h3 style={{ margin: 0, fontSize: '1rem' }}>History</h3>
        <span className="grow" />
        <span className="ct-sub">
          {present} day{present === 1 ? '' : 's'} present · {fmtDuration(total)} effective
        </span>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Period">
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
      </div>

      {error && <div className="wc-error" style={{ marginBottom: '1rem' }}>{error}</div>}

      <div className="ct-table-wrap">
        <table className="ct-table">
          <thead>
            <tr>
              <th aria-label="Expand" />
              <th>Date</th>
              <th>Status</th>
              <th>First in</th>
              <th>Last out</th>
              <th>Effective</th>
              <th>Gross</th>
              <th>Sessions</th>
            </tr>
          </thead>
          <tbody>
            {!data && !error && (
              <tr><td colSpan={8} className="ct-empty">Loading…</td></tr>
            )}
            {rows.map((r) => {
              const isOpen = open === r.date;
              const can = r.sessions.length > 0;
              return (
                <React.Fragment key={r.date}>
                  <tr className={can ? 'expandable' : ''} onClick={() => can && setOpen(isOpen ? null : r.date)}>
                    <td style={{ width: 28 }}>
                      {can && (isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />)}
                    </td>
                    <td className="strong">{fmtDay(r.date)}</td>
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
