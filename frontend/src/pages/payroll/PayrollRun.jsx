// src/pages/payroll/PayrollRun.jsx
//
// One payroll month: totals, every payslip, and the maker-checker workflow.
//
//   draft      the preparer adjusts LOP days and one-off lines, recalculates,
//              then submits
//   submitted  someone else approves (closes) it, or sends it back with a reason
//   closed     read-only; payslips and registers can be downloaded
//
// The server enforces all of this — the buttons only reflect it.

import React, { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  AlertCircle, AlertTriangle, ArrowLeft, Check, ChevronDown, ChevronRight, Download, FileText,
  Pencil, Plus, RefreshCw, Send, Trash2, Undo2,
} from 'lucide-react';

import DashboardLayout from '../../layouts/DashboardLayout';
import VaultModal from '../../components/VaultModal';
import { useAuth } from '../../context/AuthContext';
import usePermissions from '../../hooks/usePermissions';
import { payrollApi } from '../../services/api';
import { inr, inr2 } from '../../utils/inr';
import { sidebarPropsFor } from '../../utils/sidebarRole';
import { StatusPill } from './PayrollRuns';
import '../vault/vault.css';
import '../../components/clock.css';
import './payroll.css';

function Lines({ entry }) {
  return (
    <div className="pr-lines">
      <div>
        <h5>Earnings</h5>
        {entry.earnings.map((l, i) => (
          <div key={`${l.code}-${i}`} className="pr-line"><span>{l.name}</span><b>{inr(l.amount)}</b></div>
        ))}
        <div className="pr-line total"><span>Gross</span><b>{inr(entry.gross)}</b></div>
      </div>
      <div>
        <h5>Deductions</h5>
        {entry.deductions.length === 0 && <div className="pr-line"><span>None</span></div>}
        {entry.deductions.map((l, i) => (
          <div key={`${l.code}-${i}`} className="pr-line"><span>{l.name}</span><b>{inr(l.amount)}</b></div>
        ))}
        <div className="pr-line total"><span>Total</span><b>{inr(entry.total_deductions)}</b></div>
      </div>
      <div>
        <h5>Days</h5>
        <div className="pr-line"><span>Days in month</span><b>{entry.days.days_in_month}</b></div>
        <div className="pr-line"><span>Present · leave · holidays</span>
          <b>{entry.days.present} · {entry.days.paid_leave} · {entry.days.holidays}</b></div>
        <div className="pr-line"><span>Absent · unpaid leave</span>
          <b>{entry.days.absent} · {entry.days.unpaid_leave}</b></div>
        {entry.days.not_employed > 0 && (
          <div className="pr-line"><span>Before joining</span><b>{entry.days.not_employed}</b></div>
        )}
        <div className="pr-line total"><span>Paid days</span><b>{entry.days.paid_days}</b></div>
      </div>
      <div>
        <h5>Also</h5>
        {entry.reimbursements.map((r) => (
          <div key={r.id} className="pr-line"><span>{r.name} (claim)</span><b>{inr(r.amount)}</b></div>
        ))}
        {entry.employer_contributions.map((l) => (
          <div key={l.code} className="pr-line"><span>{l.name}</span><b>{inr(l.amount)}</b></div>
        ))}
        <div className="pr-line"><span>Annual CTC</span><b>{inr(entry.structure.annual_ctc)}</b></div>
        {entry.override_note && <div className="pr-line"><span>Note: {entry.override_note}</span></div>}
      </div>
    </div>
  );
}

function EditEntry({ run, entry, onClose, onSaved }) {
  const [lop, setLop] = useState(entry.lop_override ?? '');
  const [note, setNote] = useState(entry.override_note || '');
  const [adj, setAdj] = useState(entry.adjustments.length ? entry.adjustments : []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const body = {
        override_note: note,
        adjustments: adj.filter((a) => a.label && Number(a.amount) > 0)
          .map((a) => ({ kind: a.kind, label: a.label, amount: Number(a.amount) })),
      };
      if (lop === '' || lop === null) body.clear_override = true;
      else body.lop_override = Number(lop);
      onSaved(await payrollApi.adjustEntry(run.id, entry.id, body));
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  const setRow = (i, k, v) => setAdj((rows) => rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));

  return (
    <VaultModal title={`Adjust ${entry.employee.name}`} onClose={onClose} width={620}>
      <p className="pr-sub" style={{ margin: '.2rem 0 1rem' }}>
        Calculated loss of pay: <b>{entry.days.lop} day{entry.days.lop === 1 ? '' : 's'}</b>
        {' '}({entry.days.absent} absent, {entry.days.unpaid_leave} unpaid leave). Override it if attendance is
        incomplete — for example, someone worked on site without signing in.
      </p>
      <form onSubmit={save}>
        <div className="pr-form">
          <label className="pr-field">
            <span>LOP days (override)</span>
            <input type="number" min="0" max="31" step="0.5" value={lop}
              placeholder={`Calculated: ${entry.days.lop}`} onChange={(e) => setLop(e.target.value)} />
            <small>Leave empty to use the calculated figure.</small>
          </label>
          <label className="pr-field">
            <span>Note</span>
            <input value={note} maxLength={255} onChange={(e) => setNote(e.target.value)}
              placeholder="Why it was changed" />
          </label>
        </div>

        <h4 style={{ margin: '1.1rem 0 .5rem', fontSize: '.88rem' }}>One-off lines this month</h4>
        <p className="pr-sub" style={{ margin: '0 0 .6rem' }}>
          Bonus, arrears, incentive, TDS for the month, advance recovery…
        </p>
        {adj.map((a, i) => (
          <div key={i} className="pr-adj-row">
            <select value={a.kind} onChange={(e) => setRow(i, 'kind', e.target.value)} aria-label="Type">
              <option value="earning">Earning</option>
              <option value="deduction">Deduction</option>
            </select>
            <input value={a.label} maxLength={60} placeholder="Label" aria-label="Label"
              onChange={(e) => setRow(i, 'label', e.target.value)} />
            <input type="number" min="0" step="1" value={a.amount} placeholder="Amount" aria-label="Amount"
              onChange={(e) => setRow(i, 'amount', e.target.value)} />
            <button type="button" className="pr-icon-btn" aria-label="Remove line"
              onClick={() => setAdj((rows) => rows.filter((_, j) => j !== i))}>
              <Trash2 size={14} />
            </button>
          </div>
        ))}
        <button type="button" className="v-btn"
          onClick={() => setAdj((rows) => [...rows, { kind: 'earning', label: '', amount: '' }])}>
          <Plus size={13} /> Add line
        </button>

        {error && <div className="v-banner bad" style={{ marginTop: '1rem' }}><AlertCircle size={14} /><span>{error}</span></div>}
        <div className="pr-actions">
          <button type="button" className="v-btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="pr-btn-primary" disabled={busy}>
            {busy ? 'Recalculating…' : 'Save and recalculate'}
          </button>
        </div>
      </form>
    </VaultModal>
  );
}

function SendBack({ onClose, onDone, run }) {
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const go = async (e) => {
    e.preventDefault();
    setBusy(true);
    try { onDone(await payrollApi.sendBack(run.id, note)); }
    catch (err) { setError(err.message); setBusy(false); }
  };
  return (
    <VaultModal title="Send back to draft" onClose={onClose}>
      <form onSubmit={go}>
        <label className="pr-field">
          <span>What needs fixing</span>
          <textarea autoFocus required minLength={3} maxLength={500} value={note}
            onChange={(e) => setNote(e.target.value)} />
        </label>
        {error && <div className="v-banner bad" style={{ marginTop: '.8rem' }}><AlertCircle size={14} /><span>{error}</span></div>}
        <div className="pr-actions">
          <button type="button" className="v-btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="pr-btn-primary danger" disabled={busy}>Send back</button>
        </div>
      </form>
    </VaultModal>
  );
}

export default function PayrollRun() {
  const { id } = useParams();
  const { user } = useAuth();
  const { can } = usePermissions();
  const [run, setRun] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [open, setOpen] = useState(null);
  const [editing, setEditing] = useState(null);
  const [sendingBack, setSendingBack] = useState(false);
  const [query, setQuery] = useState('');

  useEffect(() => {
    let cancelled = false;
    payrollApi.run(id).then(
      (r) => { if (!cancelled) setRun(r); },
      (err) => { if (!cancelled) setError(err.message); },
    );
    return () => { cancelled = true; };
  }, [id]);

  const act = async (label, fn) => {
    setBusy(label);
    setError('');
    try { setRun(await fn()); }
    catch (err) { setError(err.message); }
    finally { setBusy(''); }
  };

  const download = async (fn) => {
    setError('');
    try { await fn(); } catch (err) { setError(err.message); }
  };

  const entries = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (run?.entries || []).filter((e) => !q || e.employee.name.toLowerCase().includes(q)
      || (e.employee.employee_code || '').toLowerCase().includes(q));
  }, [run, query]);

  const manage = can('payroll.manage');
  const draft = run?.status === 'draft';
  const warnings = (run?.entries || []).filter((e) => e.warnings?.length);
  const t = run?.totals || {};

  return (
    <DashboardLayout title="Payroll" {...sidebarPropsFor(user)}>
      <div className="pr-head">
        <Link to="/payroll" className="v-btn"><ArrowLeft size={13} /> All months</Link>
        {run && (
          <>
            <h2>{run.label}</h2>
            <StatusPill status={run.status} />
            <div className="pr-steps">
              <span className={`pr-step ${draft ? 'now' : 'done'}`}><Check size={12} /> Prepared{run.prepared_by ? ` by ${run.prepared_by}` : ''}</span>
              <ChevronRight size={12} />
              <span className={`pr-step ${run.status === 'submitted' ? 'now' : run.status === 'closed' ? 'done' : ''}`}>
                Submitted{run.submitted_by ? ` by ${run.submitted_by}` : ''}
              </span>
              <ChevronRight size={12} />
              <span className={`pr-step ${run.status === 'closed' ? 'done' : ''}`}>
                Approved{run.approved_by ? ` by ${run.approved_by}` : ''}
              </span>
            </div>
          </>
        )}
      </div>

      {error && <div className="v-banner bad"><AlertCircle size={14} /><span>{error}</span></div>}
      {run?.returned_note && draft && (
        <div className="v-banner warn"><Undo2 size={14} /><span><b>Sent back:</b> {run.returned_note}</span></div>
      )}
      {run?.status === 'submitted' && !run.can_approve && (
        <div className="v-banner info"><AlertCircle size={14} /><span>
          Waiting for approval. {run.submitted_by_id === user?.id
            ? 'You submitted this month, so another administrator has to approve it.'
            : 'Approving needs the payroll.approve permission.'}
        </span></div>
      )}
      {warnings.length > 0 && (
        <div className="v-banner warn"><AlertTriangle size={14} /><span>
          {warnings.length} payslip{warnings.length === 1 ? ' needs' : 's need'} attention: {warnings.slice(0, 3)
            .map((e) => `${e.employee.name} — ${e.warnings[0]}`).join('; ')}{warnings.length > 3 ? '…' : ''}
        </span></div>
      )}

      {run && (
        <>
          <div className="ct-tiles">
            <div className="ct-tile"><span>People</span><strong>{t.people ?? 0}</strong></div>
            <div className="ct-tile"><span>Gross</span><strong>{inr(t.gross)}</strong></div>
            <div className="ct-tile"><span>Deductions</span><strong>{inr(t.total_deductions)}</strong></div>
            <div className="ct-tile in"><span>Net pay</span><strong>{inr(t.net_pay)}</strong></div>
          </div>

          <div className="ct-toolbar">
            <input type="search" placeholder="Search name or code" aria-label="Search" value={query}
              onChange={(e) => setQuery(e.target.value)}
              style={{ height: 38, padding: '0 .7rem', borderRadius: 8, border: '1px solid var(--border2)', background: 'var(--bg2)', color: 'var(--text)', minWidth: 200 }} />
            <span className="ct-sub">
              Reimbursements {inr(t.reimbursement_total)} · Employer contributions {inr(t.employer_total)}
            </span>
            <span className="grow" />
            <button type="button" className="v-btn" onClick={() => download(() => payrollApi.downloadRegister(run.id, run.period))}>
              <Download size={13} /> Register CSV
            </button>
            <button type="button" className="v-btn" onClick={() => download(() => payrollApi.downloadSummary(run.id, run.period))}>
              <FileText size={13} /> Summary CSV
            </button>
            {draft && manage && (
              <>
                <button type="button" className="v-btn" disabled={!!busy}
                  onClick={() => act('recompute', () => payrollApi.recompute(run.id))}>
                  <RefreshCw size={13} /> {busy === 'recompute' ? 'Recalculating…' : 'Recalculate'}
                </button>
                <button type="button" className="pr-btn-primary" disabled={!!busy || !t.people}
                  onClick={() => act('submit', () => payrollApi.submit(run.id))}>
                  <Send size={14} /> {busy === 'submit' ? 'Submitting…' : 'Submit for approval'}
                </button>
              </>
            )}
            {run.status === 'submitted' && (can('payroll.approve') || manage) && (
              <button type="button" className="v-btn" onClick={() => setSendingBack(true)}>
                <Undo2 size={13} /> Send back
              </button>
            )}
            {run.can_approve && (
              <button type="button" className="pr-btn-primary" disabled={!!busy}
                onClick={() => {
                  if (window.confirm(`Approve and close ${run.label}? Payslips become final and cannot be recalculated.`)) {
                    act('approve', () => payrollApi.approve(run.id));
                  }
                }}>
                <Check size={14} /> {busy === 'approve' ? 'Closing…' : 'Approve & close month'}
              </button>
            )}
          </div>

          <div className="ct-table-wrap">
            <table className="ct-table">
              <thead>
                <tr>
                  <th aria-label="Expand" />
                  <th>Employee</th>
                  <th>Paid days</th>
                  <th>LOP</th>
                  <th>Gross</th>
                  <th>Deductions</th>
                  <th>Claims</th>
                  <th>Net pay</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {entries.length === 0 && <tr><td colSpan={9} className="ct-empty">Nobody here.</td></tr>}
                {entries.map((e) => {
                  const isOpen = open === e.id;
                  return (
                    <React.Fragment key={e.id}>
                      <tr className="expandable" onClick={() => setOpen(isOpen ? null : e.id)}>
                        <td style={{ width: 28 }}>{isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</td>
                        <td className="strong">
                          {e.employee.name}
                          {e.warnings?.length > 0 && <AlertTriangle size={12} style={{ color: 'var(--warn)', marginLeft: 6 }} />}
                          <div className="ct-sub">
                            {e.employee.employee_code || '—'} · {e.employee.department || 'No department'}
                            {e.employee.pay_type === 'stipend' ? ' · Stipend' : ''}
                          </div>
                        </td>
                        <td className="mono">{e.days.paid_days}</td>
                        <td className="mono">
                          {e.days.lop_days}
                          {e.days.lop_overridden && <span className="v-chip" style={{ marginLeft: 5 }} title={e.override_note || 'Set by an admin'}>edited</span>}
                        </td>
                        <td className="mono">{inr(e.gross)}</td>
                        <td className="mono">{inr(e.total_deductions)}</td>
                        <td className="mono">{e.reimbursement_total ? inr(e.reimbursement_total) : '—'}</td>
                        <td className="mono pr-money net">{inr2(e.net_pay)}</td>
                        <td onClick={(ev) => ev.stopPropagation()} style={{ whiteSpace: 'nowrap' }}>
                          {draft && manage && (
                            <button type="button" className="v-btn" onClick={() => setEditing(e)} aria-label={`Adjust ${e.employee.name}`}>
                              <Pencil size={12} />
                            </button>
                          )}{' '}
                          <button type="button" className="v-btn" title="Download payslip"
                            onClick={() => download(() => payrollApi.downloadPayslip(run.id, e.id))}
                            aria-label={`Payslip for ${e.employee.name}`}>
                            <FileText size={12} />
                          </button>
                        </td>
                      </tr>
                      {isOpen && (
                        <tr className="detail"><td /><td colSpan={8}><Lines entry={e} /></td></tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
      {!run && !error && <div className="card-box"><p className="pr-sub">Loading…</p></div>}

      {editing && (
        <EditEntry run={run} entry={editing} onClose={() => setEditing(null)}
          onSaved={(r) => { setRun(r); setEditing(null); }} />
      )}
      {sendingBack && (
        <SendBack run={run} onClose={() => setSendingBack(false)}
          onDone={(r) => { setRun(r); setSendingBack(false); }} />
      )}
    </DashboardLayout>
  );
}
