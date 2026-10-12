// src/pages/payroll/PayrollPeople.jsx
//
// Everyone on payroll: their current CTC and monthly fixed pay, and what is
// missing before they can be paid properly. Opening a person shows their
// compliance details (PAN, UAN, ESIC, bank) and their salary revision
// history, and lets a payroll manager add a new revision.

import React, { useEffect, useMemo, useState } from 'react';
import { AlertCircle, ChevronRight, TrendingUp } from 'lucide-react';

import DashboardLayout from '../../layouts/DashboardLayout';
import VaultModal from '../../components/VaultModal';
import { useAuth } from '../../context/AuthContext';
import usePermissions from '../../hooks/usePermissions';
import { payrollApi } from '../../services/api';
import { inr } from '../../utils/inr';
import { sidebarPropsFor } from '../../utils/sidebarRole';
import '../vault/vault.css';
import '../../components/clock.css';
import './payroll.css';

const PROFILE_FIELDS = [
  ['designation', 'Designation', 'text', 'Software Engineer'],
  ['date_of_joining', 'Date of joining', 'date'],
  ['pan', 'PAN', 'text', 'ABCDE1234F'],
  ['uan', 'UAN (PF)', 'text', '12 digits'],
  ['pf_number', 'PF member number', 'text', 'MH/BAN/0012345/000/0001234'],
  ['esic_number', 'ESIC number', 'text', '10–17 digits'],
  ['pt_state', 'Professional Tax state', 'text', 'Maharashtra'],
  ['bank_name', 'Bank', 'text', 'HDFC Bank'],
  ['bank_account', 'Account number', 'text', 'Digits only'],
  ['bank_ifsc', 'IFSC', 'text', 'HDFC0001234'],
];

export function RevisionHistory({ revisions, currentId }) {
  if (!revisions?.length) return <p className="pr-sub">No salary structure yet.</p>;
  return (
    <div className="pr-timeline">
      {revisions.map((r, i) => {
        const prev = revisions[i + 1];
        const change = prev && prev.annual_ctc ? ((r.annual_ctc - prev.annual_ctc) / prev.annual_ctc) * 100 : null;
        return (
          <div key={r.id} className={`pr-rev ${r.id === currentId ? 'current' : ''}`}>
            <div className="pr-rev-head">
              <b>{new Date(`${r.effective_from}T00:00:00`).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}</b>
              <span className="pr-money">CTC {inr(r.annual_ctc)}/yr</span>
              <span className="pr-sub">· fixed {inr(r.monthly_fixed)}/mo</span>
              {change !== null && (
                <span className={`v-chip ${change >= 0 ? 'good' : 'danger'}`}>
                  <TrendingUp size={10} /> {change >= 0 ? '+' : ''}{change.toFixed(1)}%
                </span>
              )}
              {r.id === currentId && <span className="v-chip info">current</span>}
            </div>
            <div className="pr-sub" style={{ marginTop: '.2rem' }}>
              {r.lines.map((l) => `${l.name} ${inr(l.amount)}`).join(' · ')}
            </div>
            {(r.reason || r.created_by) && (
              <div className="pr-sub" style={{ marginTop: '.15rem' }}>
                {r.reason}{r.reason && r.created_by ? ' — ' : ''}{r.created_by ? `by ${r.created_by}` : ''}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function Person({ userId, components, onClose, onChanged }) {
  const { can } = usePermissions();
  const manage = can('payroll.manage');
  const [p, setP] = useState(null);
  const [tab, setTab] = useState('salary');
  const [profile, setProfile] = useState(null);
  const [rev, setRev] = useState({ effective_from: '', annual_ctc: '', reason: '', lines: {} });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState('');

  const fixed = components.filter((c) => c.calc === 'fixed' && c.active);

  useEffect(() => {
    let cancelled = false;
    payrollApi.person(userId).then(
      (d) => {
        if (cancelled) return;
        setP(d);
        setProfile({ ...d.profile, exempt_codes: d.profile.exempt_codes || [] });
        const lines = {};
        (d.current?.lines || []).forEach((l) => { lines[l.code] = l.amount; });
        setRev((r) => ({ ...r, annual_ctc: d.current?.annual_ctc ?? '', lines }));
      },
      (err) => { if (!cancelled) setError(err.message); },
    );
    return () => { cancelled = true; };
  }, [userId]);

  const monthly = Object.values(rev.lines).reduce((n, v) => n + (Number(v) || 0), 0);

  const saveProfile = async (e) => {
    e.preventDefault();
    setBusy(true); setError(''); setSaved('');
    try {
      const body = { ...profile };
      Object.keys(body).forEach((k) => { if (body[k] === '') body[k] = null; });
      const d = await payrollApi.saveProfile(userId, body);
      setP(d); setSaved('Pay details saved.'); onChanged();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };

  const saveRevision = async (e) => {
    e.preventDefault();
    setBusy(true); setError(''); setSaved('');
    try {
      const lines = {};
      Object.entries(rev.lines).forEach(([k, v]) => { if (Number(v) > 0) lines[k] = Number(v); });
      const d = await payrollApi.addRevision(userId, {
        effective_from: rev.effective_from, annual_ctc: Number(rev.annual_ctc), lines, reason: rev.reason || null,
      });
      setP(d); setSaved('Salary revision added.'); onChanged();
      setRev((r) => ({ ...r, effective_from: '', reason: '' }));
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };

  return (
    <VaultModal title={p ? p.name : 'Loading…'} onClose={onClose} width={760}>
      {p && (
        <>
          <div className="pr-sub" style={{ marginBottom: '.8rem' }}>
            {p.employee_code || '—'} · {p.department || 'No department'} · {p.email || ''}
          </div>
          <div className="pr-tabs">
            <button type="button" className={`pr-tab ${tab === 'salary' ? 'active' : ''}`} onClick={() => setTab('salary')}>Salary &amp; revisions</button>
            <button type="button" className={`pr-tab ${tab === 'profile' ? 'active' : ''}`} onClick={() => setTab('profile')}>Pay details &amp; compliance</button>
          </div>
          {error && <div className="v-banner bad"><AlertCircle size={14} /><span>{error}</span></div>}
          {saved && <div className="v-banner ok"><span>{saved}</span></div>}

          {tab === 'salary' && (
            <>
              <RevisionHistory revisions={p.revisions} currentId={p.current?.id} />
              {manage && (
                <form onSubmit={saveRevision} className="card-box" style={{ marginTop: '1rem', marginBottom: 0, padding: '1rem' }}>
                  <h4 style={{ margin: '0 0 .7rem' }}>New revision</h4>
                  {fixed.length === 0 ? (
                    <p className="pr-sub">Add fixed earnings (Basic, HRA…) under Pay components first.</p>
                  ) : (
                    <>
                      <div className="pr-form three">
                        <label className="pr-field">
                          <span>Effective from</span>
                          <input type="date" required value={rev.effective_from}
                            onChange={(e) => setRev({ ...rev, effective_from: e.target.value })} />
                        </label>
                        <label className="pr-field">
                          <span>Annual CTC (₹)</span>
                          <input type="number" min="0" step="1" required value={rev.annual_ctc}
                            onChange={(e) => setRev({ ...rev, annual_ctc: e.target.value })} />
                          <small>Fixed × 12 = {inr(monthly * 12)}</small>
                        </label>
                        <label className="pr-field">
                          <span>Reason</span>
                          <input maxLength={255} value={rev.reason} placeholder="Annual appraisal"
                            onChange={(e) => setRev({ ...rev, reason: e.target.value })} />
                        </label>
                        {fixed.map((c) => (
                          <label key={c.code} className="pr-field">
                            <span>{c.name} / month</span>
                            <input type="number" min="0" step="1" value={rev.lines[c.code] ?? ''}
                              placeholder={c.kind === 'deduction' ? 'Deduction' : '0'}
                              onChange={(e) => setRev({ ...rev, lines: { ...rev.lines, [c.code]: e.target.value } })} />
                          </label>
                        ))}
                      </div>
                      <div className="pr-actions">
                        <span className="pr-sub" style={{ marginRight: 'auto', alignSelf: 'center' }}>
                          Monthly fixed: <b>{inr(monthly)}</b>
                        </span>
                        <button type="submit" className="pr-btn-primary" disabled={busy}>Add revision</button>
                      </div>
                    </>
                  )}
                </form>
              )}
            </>
          )}

          {tab === 'profile' && profile && (
            <form onSubmit={saveProfile}>
              <div className="pr-form three">
                <label className="pr-field">
                  <span>Pay type</span>
                  <select value={profile.pay_type} disabled={!manage}
                    onChange={(e) => setProfile({ ...profile, pay_type: e.target.value })}>
                    <option value="salary">Salary</option>
                    <option value="stipend">Stipend (intern / trainee)</option>
                  </select>
                </label>
                {PROFILE_FIELDS.map(([k, label, type, ph]) => (
                  <label key={k} className="pr-field">
                    <span>{label}</span>
                    <input type={type} value={profile[k] ?? ''} placeholder={ph} disabled={!manage}
                      onChange={(e) => setProfile({ ...profile, [k]: e.target.value })} />
                  </label>
                ))}
                <div className="pr-field full">
                  <span>Components that do not apply to this person</span>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '.8rem', marginTop: '.2rem' }}>
                    {components.filter((c) => c.calc !== 'fixed').map((c) => (
                      <label key={c.code} className="pr-check">
                        <input type="checkbox" disabled={!manage}
                          checked={profile.exempt_codes.includes(c.code)}
                          onChange={(e) => setProfile({
                            ...profile,
                            exempt_codes: e.target.checked
                              ? [...profile.exempt_codes, c.code]
                              : profile.exempt_codes.filter((x) => x !== c.code),
                          })} />
                        {c.name}
                      </label>
                    ))}
                    {components.filter((c) => c.calc !== 'fixed').length === 0 && (
                      <span className="pr-sub">No calculated components yet.</span>
                    )}
                  </div>
                  <small>For example, an employee who has opted out of PF.</small>
                </div>
              </div>
              {manage && (
                <div className="pr-actions">
                  <button type="submit" className="pr-btn-primary" disabled={busy}>Save pay details</button>
                </div>
              )}
            </form>
          )}
        </>
      )}
      {!p && error && <div className="v-banner bad"><AlertCircle size={14} /><span>{error}</span></div>}
    </VaultModal>
  );
}

export default function PayrollPeople() {
  const { user } = useAuth();
  const [rows, setRows] = useState(null);
  const [components, setComponents] = useState([]);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(null);
  const [query, setQuery] = useState('');
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    Promise.all([payrollApi.people(), payrollApi.components()]).then(
      ([p, c]) => { if (!cancelled) { setRows(p); setComponents(c); } },
      (err) => { if (!cancelled) setError(err.message); },
    );
    return () => { cancelled = true; };
  }, [tick]);

  const list = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (rows || []).filter((r) => !q || r.name.toLowerCase().includes(q)
      || (r.employee_code || '').toLowerCase().includes(q) || (r.department || '').toLowerCase().includes(q));
  }, [rows, query]);

  const incomplete = (rows || []).filter((r) => r.missing.length).length;

  return (
    <DashboardLayout title="Salaries" {...sidebarPropsFor(user)}>
      <div className="pr-head">
        <div>
          <h2>Salaries</h2>
          <div className="pr-sub">
            {rows ? `${rows.length} people` : ''}{incomplete ? ` · ${incomplete} missing details` : ''}
          </div>
        </div>
        <span className="grow" />
        <input type="search" placeholder="Search name, code or department" value={query} aria-label="Search"
          onChange={(e) => setQuery(e.target.value)}
          style={{ height: 38, padding: '0 .7rem', borderRadius: 8, border: '1px solid var(--border2)', background: 'var(--bg2)', color: 'var(--text)', minWidth: 240 }} />
      </div>

      {error && <div className="v-banner bad"><AlertCircle size={14} /><span>{error}</span></div>}

      <div className="ct-table-wrap">
        <table className="ct-table">
          <thead>
            <tr><th>Name</th><th>Department</th><th>Pay type</th><th>Annual CTC</th><th>Monthly fixed</th><th>Since</th><th>Missing</th><th aria-label="Open" /></tr>
          </thead>
          <tbody>
            {!rows && !error && <tr><td colSpan={8} className="ct-empty">Loading…</td></tr>}
            {list.map((r) => (
              <tr key={r.user_id} className="expandable" onClick={() => setOpen(r.user_id)}>
                <td className="strong">{r.name}<div className="ct-sub">{r.employee_code || '—'}{r.designation ? ` · ${r.designation}` : ''}</div></td>
                <td>{r.department || '—'}</td>
                <td>{r.pay_type === 'stipend' ? 'Stipend' : 'Salary'}</td>
                <td className="mono">{inr(r.annual_ctc)}</td>
                <td className="mono">{inr(r.monthly_fixed)}</td>
                <td className="mono">{r.effective_from || '—'}</td>
                <td>
                  <span className="pr-missing">
                    {r.missing.length === 0 ? <span className="v-chip good">complete</span>
                      : r.missing.map((m) => <span key={m} className="v-chip warn">{m.replaceAll('_', ' ')}</span>)}
                  </span>
                </td>
                <td><ChevronRight size={14} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {open && (
        <Person userId={open} components={components} onClose={() => setOpen(null)}
          onChanged={() => setTick((n) => n + 1)} />
      )}
    </DashboardLayout>
  );
}
