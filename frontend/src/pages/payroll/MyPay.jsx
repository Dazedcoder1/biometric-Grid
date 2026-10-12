// src/pages/payroll/MyPay.jsx
//
// My pay: payslips for every closed month (PDF download), my current salary
// structure and its revision history, and my expense claims.

import React, { useEffect, useState } from 'react';
import { AlertCircle, FileDown, Plus, Trash2 } from 'lucide-react';

import DashboardLayout from '../../layouts/DashboardLayout';
import { useAuth } from '../../context/AuthContext';
import { payrollApi } from '../../services/api';
import { inr } from '../../utils/inr';
import { sidebarPropsFor } from '../../utils/sidebarRole';
import { RevisionHistory } from './PayrollPeople';
import { ClaimStatus } from './Reimbursements';
import '../vault/vault.css';
import '../../components/clock.css';
import './payroll.css';

const CATEGORIES = ['Travel', 'Local conveyance', 'Food', 'Internet / phone', 'Fuel', 'Medical', 'Equipment', 'Other'];

function today() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export default function MyPay() {
  const { user } = useAuth();
  const [tab, setTab] = useState('payslips');
  const [slips, setSlips] = useState(null);
  const [me, setMe] = useState(null);
  const [claims, setClaims] = useState(null);
  const [error, setError] = useState('');
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([payrollApi.myPayslips(), payrollApi.me(), payrollApi.myClaims()]).then(
      ([s, m, c]) => { if (!cancelled) { setSlips(s); setMe(m); setClaims(c); } },
      (err) => { if (!cancelled) setError(err.message); },
    );
    return () => { cancelled = true; };
  }, []);

  const download = async (id) => {
    setError('');
    try { await payrollApi.downloadMyPayslip(id); } catch (err) { setError(err.message); }
  };

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const c = await payrollApi.submitClaim({ ...form, amount: Number(form.amount) });
      setClaims((list) => [c, ...(list || [])]);
      setForm(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const withdraw = async (c) => {
    if (!window.confirm(`Withdraw the ${inr(c.amount)} ${c.category} claim?`)) return;
    try {
      await payrollApi.withdrawClaim(c.id);
      setClaims((list) => list.filter((x) => x.id !== c.id));
    } catch (err) {
      setError(err.message);
    }
  };

  const cur = me?.current;

  return (
    <DashboardLayout title="My Pay" {...sidebarPropsFor(user)}>
      {error && <div className="v-banner bad"><AlertCircle size={14} /><span>{error}</span></div>}

      {cur && (
        <div className="ct-tiles">
          <div className="ct-tile"><span>Annual CTC</span><strong>{inr(cur.annual_ctc)}</strong></div>
          <div className="ct-tile"><span>Monthly fixed</span><strong>{inr(cur.monthly_fixed)}</strong></div>
          <div className="ct-tile in"><span>Last net pay</span><strong>{slips?.[0] ? inr(slips[0].net_pay) : '—'}</strong></div>
          <div className="ct-tile"><span>Pay type</span><strong style={{ fontSize: '1.05rem' }}>{me.profile.pay_type === 'stipend' ? 'Stipend' : 'Salary'}</strong></div>
        </div>
      )}

      <div className="pr-tabs">
        <button type="button" className={`pr-tab ${tab === 'payslips' ? 'active' : ''}`} onClick={() => setTab('payslips')}>Payslips</button>
        <button type="button" className={`pr-tab ${tab === 'salary' ? 'active' : ''}`} onClick={() => setTab('salary')}>Salary &amp; revisions</button>
        <button type="button" className={`pr-tab ${tab === 'claims' ? 'active' : ''}`} onClick={() => setTab('claims')}>Expense claims</button>
      </div>

      {tab === 'payslips' && (
        <div className="ct-table-wrap">
          <table className="ct-table">
            <thead><tr><th>Month</th><th>Paid days</th><th>LOP</th><th>Gross</th><th>Deductions</th><th>Net pay</th><th aria-label="Download" /></tr></thead>
            <tbody>
              {!slips && !error && <tr><td colSpan={7} className="ct-empty">Loading…</td></tr>}
              {slips && slips.length === 0 && (
                <tr><td colSpan={7} className="ct-empty">No payslips yet — they appear once a payroll month is approved.</td></tr>
              )}
              {(slips || []).map((s) => (
                <tr key={s.id}>
                  <td className="strong">{s.label}</td>
                  <td className="mono">{s.paid_days}</td>
                  <td className="mono">{s.lop_days}</td>
                  <td className="mono">{inr(s.gross)}</td>
                  <td className="mono">{inr(s.total_deductions)}</td>
                  <td className="mono pr-money net">{inr(s.net_pay)}</td>
                  <td>
                    <button type="button" className="v-btn" onClick={() => download(s.id)}>
                      <FileDown size={13} /> PDF
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'salary' && me && (
        <div className="card-box">
          {cur && (
            <div className="pr-lines" style={{ marginBottom: '.8rem' }}>
              <div>
                <h5>Current monthly structure</h5>
                {cur.lines.map((l) => (
                  <div key={l.code} className="pr-line"><span>{l.name}</span><b>{inr(l.amount)}</b></div>
                ))}
                <div className="pr-line total"><span>Monthly fixed</span><b>{inr(cur.monthly_fixed)}</b></div>
              </div>
            </div>
          )}
          <h4 style={{ margin: '0 0 .7rem' }}>Revision history</h4>
          <RevisionHistory revisions={me.revisions} currentId={cur?.id} />
          <p className="pr-sub" style={{ marginTop: '.6rem' }}>
            Statutory deductions (PF, ESI, Professional Tax…) are worked out each month from these figures and
            shown on your payslip.
          </p>
        </div>
      )}

      {tab === 'claims' && (
        <>
          <div className="pr-head">
            <span className="pr-sub">Approved claims are paid with your next salary.</span>
            <span className="grow" />
            {!form && (
              <button type="button" className="pr-btn-primary"
                onClick={() => setForm({ category: 'Travel', amount: '', expense_date: today(), description: '', reference: '' })}>
                <Plus size={14} /> New claim
              </button>
            )}
          </div>

          {form && (
            <form onSubmit={submit} className="card-box" style={{ padding: '1rem' }}>
              <div className="pr-form three">
                <label className="pr-field">
                  <span>Category</span>
                  <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                    {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
                  </select>
                </label>
                <label className="pr-field">
                  <span>Amount (₹)</span>
                  <input type="number" min="1" step="0.01" required value={form.amount} autoFocus
                    onChange={(e) => setForm({ ...form, amount: e.target.value })} />
                </label>
                <label className="pr-field">
                  <span>Date of expense</span>
                  <input type="date" required max={today()} value={form.expense_date}
                    onChange={(e) => setForm({ ...form, expense_date: e.target.value })} />
                </label>
                <label className="pr-field" style={{ gridColumn: 'span 2' }}>
                  <span>What it was for</span>
                  <input maxLength={500} value={form.description}
                    onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Cab to client site, Pune" />
                </label>
                <label className="pr-field">
                  <span>Bill / invoice no.</span>
                  <input maxLength={120} value={form.reference}
                    onChange={(e) => setForm({ ...form, reference: e.target.value })} />
                </label>
              </div>
              <div className="pr-actions">
                <button type="button" className="v-btn" onClick={() => setForm(null)}>Cancel</button>
                <button type="submit" className="pr-btn-primary" disabled={busy}>{busy ? 'Submitting…' : 'Submit claim'}</button>
              </div>
            </form>
          )}

          <div className="ct-table-wrap">
            <table className="ct-table">
              <thead><tr><th>Date</th><th>Category</th><th>Details</th><th>Amount</th><th>Status</th><th aria-label="Withdraw" /></tr></thead>
              <tbody>
                {!claims && !error && <tr><td colSpan={6} className="ct-empty">Loading…</td></tr>}
                {claims && claims.length === 0 && <tr><td colSpan={6} className="ct-empty">No claims yet.</td></tr>}
                {(claims || []).map((c) => (
                  <tr key={c.id}>
                    <td className="mono">{c.expense_date}</td>
                    <td>{c.category}</td>
                    <td>
                      {c.description || '—'}
                      {c.decision_note && <div className="ct-sub">Note: {c.decision_note}</div>}
                    </td>
                    <td className="mono strong">{inr(c.amount)}</td>
                    <td><ClaimStatus claim={c} /></td>
                    <td>{c.status === 'pending' && (
                      <button type="button" className="v-btn danger" onClick={() => withdraw(c)} aria-label="Withdraw claim">
                        <Trash2 size={12} />
                      </button>
                    )}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </DashboardLayout>
  );
}
