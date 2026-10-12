// src/pages/documents/LetterTemplates.jsx
//
// The letterhead every letter is printed on, and the wording of each letter
// type. Every saved change to a template's wording is kept as a version;
// letters already issued keep the wording they were issued with.

import React, { useEffect, useRef, useState } from 'react';
import { AlertCircle, History, Pencil, Plus, Sparkles } from 'lucide-react';

import DashboardLayout from '../../layouts/DashboardLayout';
import VaultModal from '../../components/VaultModal';
import { useAuth } from '../../context/AuthContext';
import usePermissions from '../../hooks/usePermissions';
import { documentsApi } from '../../services/api';
import { sidebarPropsFor } from '../../utils/sidebarRole';
import { AccessLogButton } from './shared';
import { fmtDateTime } from '../../utils/docFormat';

const LETTERHEAD = [
  ['company_name', 'Registered company name', 'Northwind Traders Pvt Ltd'],
  ['address', 'Address (one line each)', '4th Floor, Baner Road\nPune 411045, Maharashtra', 'textarea'],
  ['contact_line', 'Contact line', '+91 20 4000 1234 · hr@company.in · company.in'],
  ['cin', 'CIN', 'U72900PN2019PTC123456'],
  ['signatory_name', 'Signs letters as', 'Priya Kulkarni'],
  ['signatory_title', 'Signatory title', 'Head of People'],
  ['footer', 'Footer', 'Registered office address, or a confidentiality line'],
  ['reference_prefix', 'Reference prefix', 'NWT'],
];

function Letterhead() {
  const { can } = usePermissions();
  const [f, setF] = useState(null);
  const [saved, setSaved] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    documentsApi.letterhead().then((d) => { if (!cancelled) setF(d); }, (err) => { if (!cancelled) setError(err.message); });
    return () => { cancelled = true; };
  }, []);
  const save = async (e) => {
    e.preventDefault();
    setSaved(''); setError('');
    try { setF(await documentsApi.saveLetterhead(f)); setSaved('Letterhead saved.'); }
    catch (err) { setError(err.message); }
  };
  if (!f) return error ? <div className="v-banner bad"><span>{error}</span></div> : null;
  const manage = can('documents.manage');
  return (
    <form className="card-box" onSubmit={save} style={{ marginBottom: '1.2rem' }}>
      <h4 style={{ margin: '0 0 .3rem' }}>Letterhead</h4>
      <p className="pr-sub" style={{ margin: '0 0 .9rem' }}>Printed on every letter. Issued letters keep the letterhead they were issued with.</p>
      <div className="pr-form three">
        {LETTERHEAD.map(([k, label, ph, type]) => (
          <label key={k} className="pr-field" style={type === 'textarea' ? { gridRow: 'span 2' } : undefined}>
            <span>{label}</span>
            {type === 'textarea'
              ? <textarea value={f[k] || ''} placeholder={ph} disabled={!manage} rows={3} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
              : <input value={f[k] || ''} placeholder={ph} disabled={!manage} onChange={(e) => setF({ ...f, [k]: e.target.value })} />}
          </label>
        ))}
      </div>
      {error && <div className="v-banner bad" style={{ marginTop: '.8rem' }}><AlertCircle size={14} /><span>{error}</span></div>}
      {saved && <div className="v-banner ok" style={{ marginTop: '.8rem' }}><span>{saved}</span></div>}
      {manage && <div className="pr-actions"><button type="submit" className="pr-btn-primary">Save letterhead</button></div>}
    </form>
  );
}

function Editor({ initial, kinds, fields, onClose, onSaved }) {
  const [f, setF] = useState(() => ({ kind: 'other', name: '', subject: '', body: '', active: true, note: '', ...initial }));
  const [versions, setVersions] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const ref = useRef(null);
  const editing = !!initial?.id;

  const insert = (name) => {
    const el = ref.current;
    const token = `{{${name}}}`;
    if (!el) { setF({ ...f, body: `${f.body}${token}` }); return; }
    const start = el.selectionStart ?? f.body.length;
    const end = el.selectionEnd ?? start;
    const body = f.body.slice(0, start) + token + f.body.slice(end);
    setF({ ...f, body });
    requestAnimationFrame(() => { el.focus(); el.setSelectionRange(start + token.length, start + token.length); });
  };

  const save = async (e) => {
    e.preventDefault();
    setBusy(true); setError('');
    try {
      onSaved(editing
        ? await documentsApi.updateTemplate(initial.id, { name: f.name, subject: f.subject, body: f.body, active: f.active, note: f.note || null })
        : await documentsApi.createTemplate({ kind: f.kind, name: f.name, subject: f.subject, body: f.body }));
    } catch (err) { setError(err.message); setBusy(false); }
  };

  const showVersions = async () => {
    try { setVersions(await documentsApi.templateVersions(initial.id)); } catch (err) { setError(err.message); }
  };

  return (
    <VaultModal title={editing ? `Edit ${initial.name}` : 'New template'} onClose={onClose} width={860}>
      <form onSubmit={save} style={{ marginTop: '.8rem' }}>
        <div className="pr-form three">
          <label className="pr-field">
            <span>Letter type</span>
            <select value={f.kind} disabled={editing} onChange={(e) => setF({ ...f, kind: e.target.value })}>
              {kinds.map((k) => <option key={k.kind} value={k.kind}>{k.label}</option>)}
            </select>
          </label>
          <label className="pr-field">
            <span>Template name</span>
            <input required minLength={2} maxLength={120} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
          </label>
          <label className="pr-field">
            <span>Subject</span>
            <input required minLength={2} maxLength={200} value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })} />
          </label>
        </div>
        <div style={{ marginTop: '.8rem' }}>
          <span className="pr-sub">Insert a field — dashed ones fill in automatically, the rest are asked for when issuing:</span>
          <div className="doc-chips">
            {fields.auto.map((x) => <button type="button" key={x.name} className="doc-chip auto" title={x.label} onClick={() => insert(x.name)}>{x.name}</button>)}
            {fields.manual.map((x) => <button type="button" key={x.name} className="doc-chip" title={x.label} onClick={() => insert(x.name)}>{x.name}</button>)}
          </div>
          <textarea ref={ref} className="doc-editor" required minLength={10} value={f.body}
            onChange={(e) => setF({ ...f, body: e.target.value })} />
          <small className="pr-sub">**bold** · blank line = new paragraph · any {'{{new_field}}'} you invent is asked for when issuing.</small>
        </div>
        {editing && (
          <div className="pr-form" style={{ marginTop: '.8rem' }}>
            <label className="pr-field">
              <span>What changed (kept with this version)</span>
              <input maxLength={255} value={f.note || ''} onChange={(e) => setF({ ...f, note: e.target.value })} />
            </label>
            <label className="pr-check" style={{ alignSelf: 'end' }}>
              <input type="checkbox" checked={f.active} onChange={(e) => setF({ ...f, active: e.target.checked })} /> Available for new letters
            </label>
          </div>
        )}
        {error && <div className="v-banner bad" style={{ marginTop: '1rem' }}><AlertCircle size={14} /><span>{error}</span></div>}
        <div className="pr-actions" style={{ justifyContent: 'space-between' }}>
          <div className="doc-card-actions">
            {editing && <button type="button" className="v-btn" onClick={showVersions}><History size={13} /> Versions ({initial.version})</button>}
            {editing && <AccessLogButton targetType="letter_template" targetId={initial.id} title={initial.name} />}
          </div>
          <div className="doc-card-actions">
            <button type="button" className="v-btn" onClick={onClose}>Cancel</button>
            <button type="submit" className="pr-btn-primary" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
          </div>
        </div>
      </form>
      {versions && (
        <div className="pr-timeline" style={{ marginTop: '1rem' }}>
          {versions.map((v) => (
            <div key={v.version} className={`pr-rev ${v.version === initial.version ? 'current' : ''}`}>
              <div className="pr-rev-head"><b>Version {v.version}</b><span className="pr-sub">{fmtDateTime(v.created_at)}{v.created_by ? ` · ${v.created_by}` : ''}</span></div>
              {v.note && <div className="pr-sub">{v.note}</div>}
              <details style={{ marginTop: '.3rem' }}>
                <summary className="pr-sub" style={{ cursor: 'pointer' }}>Show wording</summary>
                <div className="doc-letter" style={{ marginTop: '.4rem' }}>{v.subject}{'\n\n'}{v.body}</div>
              </details>
            </div>
          ))}
        </div>
      )}
    </VaultModal>
  );
}

export default function LetterTemplates() {
  const { user } = useAuth();
  const { can } = usePermissions();
  const [rows, setRows] = useState(null);
  const [fields, setFields] = useState({ auto: [], manual: [], kinds: [] });
  const [editing, setEditing] = useState(null);
  const [error, setError] = useState('');
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    Promise.all([documentsApi.templates(), documentsApi.fields()]).then(
      ([t, f]) => { if (!cancelled) { setRows(t); setFields(f); } },
      (err) => { if (!cancelled) setError(err.message); },
    );
    return () => { cancelled = true; };
  }, [tick]);

  const starters = async () => {
    setError('');
    try {
      const r = await documentsApi.addStarters();
      if (!r.added.length) setError('Every letter type already has a template.');
      setTick((n) => n + 1);
    } catch (err) { setError(err.message); }
  };

  const manage = can('documents.manage');

  return (
    <DashboardLayout title="Letter Templates" {...sidebarPropsFor(user)}>
      <Letterhead />
      <div className="pr-head">
        <div>
          <h2>Templates</h2>
          <div className="pr-sub">The wording of each letter. Starter templates are a plain starting point — read and adapt them to your policies.</div>
        </div>
        <span className="grow" />
        {manage && (
          <>
            <button type="button" className="v-btn" onClick={starters}><Sparkles size={13} /> Add starter templates</button>
            <button type="button" className="pr-btn-primary" onClick={() => setEditing({})}><Plus size={14} /> New template</button>
          </>
        )}
      </div>
      {error && <div className="v-banner warn"><AlertCircle size={14} /><span>{error}</span></div>}
      <div className="ct-table-wrap">
        <table className="ct-table">
          <thead><tr><th>Template</th><th>Type</th><th>Fields asked for</th><th>Version</th><th>Status</th><th aria-label="Edit" /></tr></thead>
          <tbody>
            {!rows && !error && <tr><td colSpan={6} className="ct-empty">Loading…</td></tr>}
            {rows && rows.length === 0 && <tr><td colSpan={6} className="ct-empty">No templates yet — add the starter set to begin.</td></tr>}
            {(rows || []).map((t) => (
              <tr key={t.id}>
                <td className="strong">{t.name}<div className="ct-sub">{t.subject}</div></td>
                <td>{t.kind_label}</td>
                <td className="ct-sub">{t.fields.filter((x) => !x.auto).map((x) => x.label).join(', ') || 'None'}</td>
                <td className="mono">v{t.version}</td>
                <td>{t.active ? <span className="v-chip good">in use</span> : <span className="v-chip">off</span>}</td>
                <td>{manage && <button type="button" className="v-btn" onClick={() => setEditing(t)} aria-label={`Edit ${t.name}`}><Pencil size={12} /></button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editing && (
        <Editor initial={editing.id ? editing : null} kinds={fields.kinds} fields={fields}
          onClose={() => setEditing(null)} onSaved={() => { setEditing(null); setTick((n) => n + 1); }} />
      )}
    </DashboardLayout>
  );
}
