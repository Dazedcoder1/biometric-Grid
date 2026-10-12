// src/pages/payroll/Reimbursements.jsx
//
// Expense claims to decide. A Tenant Admin sees everyone's; an Org Admin sees
// the employees in their own department. Nobody decides their own claim.
// Approved claims are paid with the next payroll month that is prepared.

import React, { useEffect, useState } from 'react';
import { AlertCircle, Check, X } from 'lucide-react';

import DashboardLayout from '../../layouts/DashboardLayout';
import VaultModal from '../../components/VaultModal';
import { useAuth } from '../../context/AuthContext';
import { payrollApi } from '../../services/api';
import { inr } from '../../utils/inr';
import { sidebarPropsFor } from '../../utils/sidebarRole';
import '../vault/vault.css';
import '../../components/clock.css';
import './payroll.css';

const TABS = ['pending', 'approved', 'paid', 'rejected', 'all'];

export function ClaimStatus({ claim }) {
  return <span className={`pr-status ${claim.status}`}>{claim.status}</span>;
}

export default function Reimbursements() {
  const { user } = useAuth();
  const [tab, setTab] = useState('pending');
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');
  const [rejecting, setRejecting] = useState(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(0);

  useEffect(() => {
    let cancelled = false;
    payrollApi.claims(tab).then(
      (r) => { if (!cancelled) { setRows(r); setError(''); } },
      (err) => { if (!cancelled) setError(err.message); },
    );
    return () => { cancelled = true; };
  }, [tab]);

  const decide = async (claim, approve, why) => {
    setBusy(claim.id);
    setError('');
    try {
      const updated = await payrollApi.decideClaim(claim.id, approve, why);
      setRows((list) => (tab === 'all' ? list.map((x) => (x.id === updated.id ? updated : x))
        : list.filter((x) => x.id !== updated.id)));
      setRejecting(null);
      setNote('');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(0);
    }
  };

  const total = (rows || []).reduce((n, r) => n + r.amount, 0);

  return (
    <DashboardLayout title="Expense Claims" {...sidebarPropsFor(user)}>
      <div className="pr-head">
        <div>
          <h2>Expense claims</h2>
          <div className="pr-sub">Approved claims are paid with the next payroll month.</div>
        </div>
      </div>
      <div className="pr-tabs">
        {TABS.map((t) => (
          <button key={t} type="button" className={`pr-tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
            {t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {error && <div className="v-banner bad"><AlertCircle size={14} /><span>{error}</span></div>}

      <div className="ct-table-wrap">
        <table className="ct-table">
          <thead>
            <tr><th>Employee</th><th>Date</th><th>Category</th><th>Details</th><th>Amount</th><th>Status</th><th aria-label="Decide" /></tr>
          </thead>
          <tbody>
            {!rows && !error && <tr><td colSpan={7} className="ct-empty">Loading…</td></tr>}
            {rows && rows.length === 0 && <tr><td colSpan={7} className="ct-empty">Nothing here.</td></tr>}
            {(rows || []).map((c) => (
              <tr key={c.id}>
                <td className="strong">{c.name}</td>
                <td className="mono">{c.expense_date}</td>
                <td>{c.category}</td>
                <td>
                  {c.description || '—'}
                  {c.reference && <div className="ct-sub">Ref: {c.reference}</div>}
                  {c.decision_note && <div className="ct-sub">Note: {c.decision_note}</div>}
                  {c.decided_by && <div className="ct-sub">Decided by {c.decided_by}</div>}
                </td>
                <td className="mono strong">{inr(c.amount)}</td>
                <td><ClaimStatus claim={c} /></td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  {c.status === 'pending' && (
                    <>
                      <button type="button" className="v-btn" disabled={busy === c.id}
                        onClick={() => decide(c, true, null)} aria-label={`Approve claim from ${c.name}`}>
                        <Check size={13} /> Approve
                      </button>{' '}
                      <button type="button" className="v-btn danger" disabled={busy === c.id}
                        onClick={() => setRejecting(c)} aria-label={`Reject claim from ${c.name}`}>
                        <X size={13} />
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows && rows.length > 0 && <p className="pr-sub" style={{ marginTop: '.6rem' }}>Total shown: {inr(total)}</p>}

      {rejecting && (
        <VaultModal title={`Reject ${inr(rejecting.amount)} from ${rejecting.name}`} onClose={() => setRejecting(null)}>
          <form onSubmit={(e) => { e.preventDefault(); decide(rejecting, false, note); }}>
            <label className="pr-field" style={{ marginTop: '.8rem' }}>
              <span>Reason — the employee sees this</span>
              <textarea autoFocus required maxLength={255} value={note} onChange={(e) => setNote(e.target.value)} />
            </label>
            <div className="pr-actions">
              <button type="button" className="v-btn" onClick={() => setRejecting(null)}>Cancel</button>
              <button type="submit" className="pr-btn-primary danger" disabled={busy === rejecting.id}>Reject claim</button>
            </div>
          </form>
        </VaultModal>
      )}
    </DashboardLayout>
  );
}
