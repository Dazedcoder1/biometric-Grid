// src/pages/payroll/PayComponents.jsx
//
// The organisation's earnings and deductions. Nothing is preloaded: PF, ESI,
// Professional Tax and the rest are added here with this organisation's own
// rates, ceilings and slabs, and switched off rather than deleted, because
// past payslips refer to them.

import React, { useEffect, useState } from 'react';
import { AlertCircle, Pencil, Plus, Trash2 } from 'lucide-react';

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

const BLANK = {
  code: '', name: '', kind: 'earning', calc: 'fixed', rate: '', employer_rate: '', base_codes: '',
  wage_ceiling: '', gross_limit: '', slabs: [], prorate: true, applies_to: 'all',
  is_statutory: false, active: true, sort_order: 100,
};

function describe(c) {
  if (c.calc === 'fixed') return `From salary structure${c.prorate ? ', pro-rated' : ''}`;
  if (c.calc === 'percent') {
    let s = `${c.rate}% of ${c.base_codes || 'gross'}`;
    if (c.wage_ceiling != null) s += `, base capped at ${inr(c.wage_ceiling)}`;
    if (c.employer_rate) s += ` · employer ${c.employer_rate}%`;
    if (c.gross_limit != null) s += ` · only if gross ≤ ${inr(c.gross_limit)}`;
    return s;
  }
  return (c.slabs || []).map((s) => `${s.upto == null ? 'above' : `≤ ${inr(s.upto)}`}: ${inr(s.amount)}`).join(' · ');
}

const num = (v) => (v === '' || v === null || v === undefined ? null : Number(v));

function Editor({ initial, onClose, onSaved }) {
  const [f, setF] = useState(() => ({
    ...BLANK, ...initial,
    rate: initial?.rate ?? '', employer_rate: initial?.employer_rate ?? '',
    wage_ceiling: initial?.wage_ceiling ?? '', gross_limit: initial?.gross_limit ?? '',
    base_codes: initial?.base_codes ?? '', slabs: initial?.slabs ?? [],
  }));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const editing = !!initial?.id;
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    const body = {
      ...f,
      rate: num(f.rate), employer_rate: num(f.employer_rate),
      wage_ceiling: num(f.wage_ceiling), gross_limit: num(f.gross_limit),
      base_codes: f.base_codes || null, sort_order: Number(f.sort_order) || 100,
      slabs: f.calc === 'slab' ? f.slabs.map((s) => ({ upto: num(s.upto), amount: Number(s.amount) || 0 })) : null,
    };
    delete body.id;
    try {
      onSaved(editing ? await payrollApi.updateComponent(initial.id, body) : await payrollApi.createComponent(body));
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <VaultModal title={editing ? `Edit ${initial.code}` : 'New pay component'} onClose={onClose} width={640}>
      <form onSubmit={save} style={{ marginTop: '.8rem' }}>
        <div className="pr-form three">
          <label className="pr-field">
            <span>Code</span>
            <input value={f.code} disabled={editing} required maxLength={32} placeholder="BASIC"
              onChange={(e) => set('code', e.target.value.toUpperCase())} autoFocus={!editing} />
          </label>
          <label className="pr-field" style={{ gridColumn: 'span 2' }}>
            <span>Name on payslip</span>
            <input value={f.name} required maxLength={80} placeholder="Basic salary"
              onChange={(e) => set('name', e.target.value)} />
          </label>
          <label className="pr-field">
            <span>Type</span>
            <select value={f.kind} onChange={(e) => set('kind', e.target.value)}>
              <option value="earning">Earning</option>
              <option value="deduction">Deduction</option>
            </select>
          </label>
          <label className="pr-field">
            <span>Calculated as</span>
            <select value={f.calc} onChange={(e) => set('calc', e.target.value)}>
              <option value="fixed">Fixed monthly amount</option>
              <option value="percent">Percentage of a base</option>
              <option value="slab">Slab by gross pay</option>
            </select>
          </label>
          <label className="pr-field">
            <span>Applies to</span>
            <select value={f.applies_to} onChange={(e) => set('applies_to', e.target.value)}>
              <option value="all">Salary and stipend</option>
              <option value="salary">Salaried only</option>
              <option value="stipend">Stipend only</option>
            </select>
          </label>

          {f.calc === 'percent' && (
            <>
              <label className="pr-field">
                <span>Employee rate %</span>
                <input type="number" min="0" max="100" step="0.01" required value={f.rate}
                  onChange={(e) => set('rate', e.target.value)} />
              </label>
              <label className="pr-field">
                <span>Employer rate %</span>
                <input type="number" min="0" max="100" step="0.01" value={f.employer_rate}
                  onChange={(e) => set('employer_rate', e.target.value)} />
                <small>Shown on the payslip and in CTC; not deducted.</small>
              </label>
              <label className="pr-field">
                <span>Base</span>
                <input value={f.base_codes} placeholder="BASIC,DA or GROSS"
                  onChange={(e) => set('base_codes', e.target.value.toUpperCase())} />
                <small>Component codes, comma separated. Empty = gross.</small>
              </label>
              <label className="pr-field">
                <span>Base capped at (₹)</span>
                <input type="number" min="0" step="1" value={f.wage_ceiling}
                  onChange={(e) => set('wage_ceiling', e.target.value)} placeholder="No cap" />
              </label>
            </>
          )}
          {(f.calc === 'percent' || f.calc === 'slab') && f.kind === 'deduction' && (
            <label className="pr-field">
              <span>Only while gross ≤ (₹)</span>
              <input type="number" min="0" step="1" value={f.gross_limit}
                onChange={(e) => set('gross_limit', e.target.value)} placeholder="Always" />
            </label>
          )}
          <label className="pr-field">
            <span>Order on payslip</span>
            <input type="number" min="0" max="10000" value={f.sort_order}
              onChange={(e) => set('sort_order', e.target.value)} />
          </label>
        </div>

        {f.calc === 'slab' && (
          <div style={{ marginTop: '1rem' }}>
            <div className="pr-sub" style={{ marginBottom: '.5rem' }}>
              Monthly gross up to an amount pays a flat figure. Leave the last limit empty for “and above”.
            </div>
            {f.slabs.map((s, i) => (
              <div key={i} className="pr-adj-row" style={{ gridTemplateColumns: '1fr 1fr 32px' }}>
                <input type="number" min="0" placeholder="Gross up to (empty = above)" value={s.upto ?? ''}
                  aria-label="Gross up to"
                  onChange={(e) => set('slabs', f.slabs.map((x, j) => (j === i ? { ...x, upto: e.target.value } : x)))} />
                <input type="number" min="0" placeholder="Amount" value={s.amount}
                  aria-label="Amount"
                  onChange={(e) => set('slabs', f.slabs.map((x, j) => (j === i ? { ...x, amount: e.target.value } : x)))} />
                <button type="button" className="pr-icon-btn" aria-label="Remove slab"
                  onClick={() => set('slabs', f.slabs.filter((_, j) => j !== i))}><Trash2 size={14} /></button>
              </div>
            ))}
            <button type="button" className="v-btn" onClick={() => set('slabs', [...f.slabs, { upto: '', amount: '' }])}>
              <Plus size={13} /> Add slab
            </button>
          </div>
        )}

        <div style={{ display: 'flex', gap: '1.2rem', flexWrap: 'wrap', marginTop: '1rem' }}>
          {f.calc === 'fixed' && (
            <label className="pr-check"><input type="checkbox" checked={f.prorate}
              onChange={(e) => set('prorate', e.target.checked)} /> Reduce for loss-of-pay days</label>
          )}
          <label className="pr-check"><input type="checkbox" checked={f.is_statutory}
            onChange={(e) => set('is_statutory', e.target.checked)} /> Statutory (PF, ESI, PT, LWF, TDS…)</label>
          <label className="pr-check"><input type="checkbox" checked={f.active}
            onChange={(e) => set('active', e.target.checked)} /> Active</label>
        </div>

        {error && <div className="v-banner bad" style={{ marginTop: '1rem' }}><AlertCircle size={14} /><span>{error}</span></div>}
        <div className="pr-actions">
          <button type="button" className="v-btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="pr-btn-primary" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
        </div>
      </form>
    </VaultModal>
  );
}

export default function PayComponents() {
  const { user } = useAuth();
  const { can } = usePermissions();
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(null);

  useEffect(() => {
    let cancelled = false;
    payrollApi.components().then(
      (r) => { if (!cancelled) setRows(r); },
      (err) => { if (!cancelled) setError(err.message); },
    );
    return () => { cancelled = true; };
  }, []);

  const saved = (c) => {
    setRows((list) => {
      const others = (list || []).filter((x) => x.id !== c.id);
      return [...others, c].sort((a, b) => a.sort_order - b.sort_order || a.code.localeCompare(b.code));
    });
    setEditing(null);
  };

  const manage = can('payroll.manage');
  const section = (kind) => (rows || []).filter((c) => c.kind === kind);

  return (
    <DashboardLayout title="Pay Components" {...sidebarPropsFor(user)}>
      <div className="pr-head">
        <div>
          <h2>Pay components</h2>
          <div className="pr-sub">
            Earnings and deductions used in salary structures and payslips. Statutory deductions are not
            preset — add PF, ESI, Professional Tax, LWF or TDS here with the rates that apply to you.
          </div>
        </div>
        <span className="grow" />
        {manage && (
          <button type="button" className="pr-btn-primary" onClick={() => setEditing({})}>
            <Plus size={14} /> New component
          </button>
        )}
      </div>

      {error && <div className="v-banner bad"><AlertCircle size={14} /><span>{error}</span></div>}

      {['earning', 'deduction'].map((kind) => (
        <div key={kind} style={{ marginBottom: '1.2rem' }}>
          <h4 style={{ margin: '0 0 .5rem', fontSize: '.85rem', color: 'var(--text2)' }}>
            {kind === 'earning' ? 'Earnings' : 'Deductions'}
          </h4>
          <div className="ct-table-wrap">
            <table className="ct-table">
              <thead>
                <tr><th>Code</th><th>Name</th><th>How it is worked out</th><th>Applies to</th><th>Status</th><th aria-label="Edit" /></tr>
              </thead>
              <tbody>
                {!rows && !error && <tr><td colSpan={6} className="ct-empty">Loading…</td></tr>}
                {rows && section(kind).length === 0 && (
                  <tr><td colSpan={6} className="ct-empty">
                    {kind === 'earning' ? 'No earnings yet — start with Basic.' : 'No deductions yet.'}
                  </td></tr>
                )}
                {section(kind).map((c) => (
                  <tr key={c.id}>
                    <td className="mono strong">{c.code}</td>
                    <td className="strong">
                      {c.name}
                      {c.is_statutory && <span className="v-chip info" style={{ marginLeft: 6 }}>statutory</span>}
                    </td>
                    <td>{describe(c)}</td>
                    <td>{{ all: 'Everyone', salary: 'Salaried', stipend: 'Stipend' }[c.applies_to]}</td>
                    <td>{c.active ? <span className="v-chip good">active</span> : <span className="v-chip">off</span>}</td>
                    <td>{manage && (
                      <button type="button" className="v-btn" onClick={() => setEditing(c)} aria-label={`Edit ${c.code}`}>
                        <Pencil size={12} />
                      </button>
                    )}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}

      {editing && <Editor initial={editing.id ? editing : null} onClose={() => setEditing(null)} onSaved={saved} />}
    </DashboardLayout>
  );
}
