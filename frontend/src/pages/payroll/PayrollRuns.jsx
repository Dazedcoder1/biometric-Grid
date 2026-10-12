// src/pages/payroll/PayrollRuns.jsx
//
// Every payroll month for the organisation, and the control to prepare the
// next one. Preparing a month that already has a draft simply recalculates
// it; a closed month cannot be prepared again.

import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AlertCircle, CalendarPlus, ChevronRight } from 'lucide-react';

import DashboardLayout from '../../layouts/DashboardLayout';
import { useAuth } from '../../context/AuthContext';
import usePermissions from '../../hooks/usePermissions';
import { payrollApi } from '../../services/api';
import { inr } from '../../utils/inr';
import { sidebarPropsFor } from '../../utils/sidebarRole';
import '../vault/vault.css';
import '../../components/clock.css';
import './payroll.css';

export function StatusPill({ status }) {
  return <span className={`pr-status ${status}`}>{status}</span>;
}

export default function PayrollRuns() {
  const { user } = useAuth();
  const { can } = usePermissions();
  const navigate = useNavigate();
  const [runs, setRuns] = useState(null);
  const [periods, setPeriods] = useState([]);
  const [period, setPeriod] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    Promise.all([payrollApi.runs(), payrollApi.periods()]).then(
      ([r, p]) => {
        if (cancelled) return;
        setRuns(r);
        setPeriods(p);
        // Suggest the newest month that is not closed yet.
        const closed = new Set(r.filter((x) => x.status === 'closed').map((x) => x.period));
        const next = p.find((x) => !closed.has(x.period));
        setPeriod(next ? next.period : '');
      },
      (err) => { if (!cancelled) setError(err.message); },
    );
    return () => { cancelled = true; };
  }, []);

  const prepare = async () => {
    setBusy(true);
    setError('');
    try {
      const run = await payrollApi.prepare(period);
      navigate(`/payroll/runs/${run.id}`);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  const byPeriod = Object.fromEntries((runs || []).map((r) => [r.period, r]));
  const chosen = byPeriod[period];

  return (
    <DashboardLayout title="Payroll" {...sidebarPropsFor(user)}>
      {error && <div className="v-banner bad"><AlertCircle size={14} /><span>{error}</span></div>}

      {can('payroll.manage') && (
        <div className="card-box" style={{ marginBottom: '1rem' }}>
          <div className="pr-head" style={{ marginBottom: 0 }}>
            <div>
              <h2>Run payroll</h2>
              <div className="pr-sub">
                Paid days come from attendance, leave and holidays. You can adjust anyone before submitting.
              </div>
            </div>
            <span className="grow" />
            <div className="pr-field" style={{ minWidth: 180 }}>
              <span>Month</span>
              <select value={period} onChange={(e) => setPeriod(e.target.value)}>
                {periods.map((p) => (
                  <option key={p.period} value={p.period}>
                    {p.label}{byPeriod[p.period] ? ` — ${byPeriod[p.period].status}` : ''}
                  </option>
                ))}
              </select>
            </div>
            {chosen && chosen.status !== 'draft' ? (
              <Link className="pr-btn-primary" to={`/payroll/runs/${chosen.id}`} style={{ alignSelf: 'flex-end', textDecoration: 'none' }}>
                Open {chosen.label} <ChevronRight size={15} />
              </Link>
            ) : (
              <button type="button" className="pr-btn-primary" onClick={prepare}
                disabled={!period || busy} style={{ alignSelf: 'flex-end' }}>
                <CalendarPlus size={15} />
                {busy ? 'Calculating…' : chosen ? 'Recalculate draft' : 'Prepare month'}
              </button>
            )}
          </div>
        </div>
      )}

      <div className="ct-table-wrap">
        <table className="ct-table">
          <thead>
            <tr>
              <th>Month</th>
              <th>Status</th>
              <th>People</th>
              <th>Gross</th>
              <th>Deductions</th>
              <th>Reimbursements</th>
              <th>Net pay</th>
              <th>Approved by</th>
              <th aria-label="Open" />
            </tr>
          </thead>
          <tbody>
            {!runs && !error && <tr><td colSpan={9} className="ct-empty">Loading…</td></tr>}
            {runs && runs.length === 0 && (
              <tr><td colSpan={9} className="ct-empty">
                No payroll months yet. Set up pay components and salary structures, then prepare a month.
              </td></tr>
            )}
            {(runs || []).map((r) => (
              <tr key={r.id} className="expandable" onClick={() => navigate(`/payroll/runs/${r.id}`)}>
                <td className="strong">{r.label}</td>
                <td><StatusPill status={r.status} /></td>
                <td className="mono">{r.totals.people ?? 0}</td>
                <td className="mono">{inr(r.totals.gross)}</td>
                <td className="mono">{inr(r.totals.total_deductions)}</td>
                <td className="mono">{inr(r.totals.reimbursement_total)}</td>
                <td className="mono pr-money net">{inr(r.totals.net_pay)}</td>
                <td>{r.approved_by || <span className="ct-sub">—</span>}</td>
                <td><ChevronRight size={14} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </DashboardLayout>
  );
}
