// src/pages/documents/Policies.jsx
//
// Leave and attendance policies, the employee handbook and anything else
// published to staff. Each publish is a new version; when a document asks for
// acknowledgement, everyone in its audience acknowledges each version, and
// this page shows who has and who has not — with a button to remind them.

import React, { useEffect, useState } from 'react';
import {
  AlertCircle, BellRing, Download, FilePlus2, Upload,
} from 'lucide-react';

import DashboardLayout from '../../layouts/DashboardLayout';
import VaultModal from '../../components/VaultModal';
import { useAuth } from '../../context/AuthContext';
import usePermissions from '../../hooks/usePermissions';
import { documentsApi } from '../../services/api';
import { sidebarPropsFor } from '../../utils/sidebarRole';
import { AccessLogButton, ExpiryPill, Pill } from './shared';
import { fmtDate, fmtDateTime, fmtSize } from '../../utils/docFormat';

const CATEGORIES = [
  ['handbook', 'Employee handbook'], ['leave_policy', 'Leave policy'],
  ['attendance_policy', 'Attendance policy'], ['policy', 'Policy'], ['other', 'Other'],
];
const ACCEPT = '.pdf,.png,.jpg,.jpeg,.docx,.txt';

function Content({ value, onChange }) {
  return (
    <div className="pr-form full" style={{ gridColumn: '1 / -1' }}>
      <div className="pr-tabs" style={{ marginBottom: '.5rem' }}>
        <button type="button" className={`pr-tab ${value.mode === 'file' ? 'active' : ''}`} onClick={() => onChange({ ...value, mode: 'file' })}>Upload a file</button>
        <button type="button" className={`pr-tab ${value.mode === 'text' ? 'active' : ''}`} onClick={() => onChange({ ...value, mode: 'text' })}>Write it here</button>
      </div>
      {value.mode === 'file' ? (
        <label className="pr-field">
          <span>PDF, Word (.docx), image or text — up to 10 MB</span>
          <input type="file" accept={ACCEPT} onChange={(e) => onChange({ ...value, file: e.target.files?.[0] || null })} style={{ height: 'auto', padding: '.5rem' }} />
        </label>
      ) : (
        <textarea className="doc-editor" style={{ minHeight: 220 }} value={value.body}
          placeholder="Write the policy text…" onChange={(e) => onChange({ ...value, body: e.target.value })} />
      )}
    </div>
  );
}

function Publish({ departments, onClose, onDone }) {
  const [f, setF] = useState({ category: 'policy', title: '', description: '', requires_ack: true, departments: [], review_by: '' });
  const [content, setContent] = useState({ mode: 'file', file: null, body: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const go = async (e) => {
    e.preventDefault();
    setBusy(true); setError('');
    try {
      onDone(await documentsApi.createPolicy({
        category: f.category, title: f.title, description: f.description, requires_ack: f.requires_ack,
        departments: f.departments.length ? f.departments : null, review_by: f.review_by || null,
        body: content.mode === 'text' ? content.body : null,
      }, content.mode === 'file' ? content.file : null));
    } catch (err) { setError(err.message); setBusy(false); }
  };
  return (
    <VaultModal title="Publish a document" onClose={onClose} width={760}>
      <form onSubmit={go} style={{ marginTop: '.8rem' }}>
        <div className="pr-form three">
          <label className="pr-field"><span>Type</span>
            <select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>
              {CATEGORIES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select></label>
          <label className="pr-field" style={{ gridColumn: 'span 2' }}><span>Title</span>
            <input required minLength={2} maxLength={200} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="Leave policy 2026" /></label>
          <label className="pr-field full"><span>Summary (optional)</span>
            <input maxLength={500} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></label>
          <label className="pr-field"><span>Review by (reminds HR)</span>
            <input type="date" value={f.review_by} onChange={(e) => setF({ ...f, review_by: e.target.value })} /></label>
          <label className="pr-field" style={{ gridColumn: 'span 2' }}><span>Who it is for</span>
            <select multiple value={f.departments.map(String)} style={{ height: 76 }}
              onChange={(e) => setF({ ...f, departments: [...e.target.selectedOptions].map((o) => Number(o.value)) })}>
              {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
            <small>Nothing selected = everyone. Ctrl/Cmd-click for several departments.</small></label>
          <label className="pr-check full"><input type="checkbox" checked={f.requires_ack} onChange={(e) => setF({ ...f, requires_ack: e.target.checked })} />
            Everyone it is for must read and acknowledge it</label>
          <Content value={content} onChange={setContent} />
        </div>
        {error && <div className="v-banner bad" style={{ marginTop: '1rem' }}><AlertCircle size={14} /><span>{error}</span></div>}
        <div className="pr-actions">
          <button type="button" className="v-btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="pr-btn-primary" disabled={busy}><FilePlus2 size={14} /> {busy ? 'Publishing…' : 'Publish'}</button>
        </div>
      </form>
    </VaultModal>
  );
}

function Detail({ id, departments, onClose, onChanged }) {
  const { can } = usePermissions();
  const manage = can('documents.manage');
  const [d, setD] = useState(null);
  const [tab, setTab] = useState('people');
  const [content, setContent] = useState({ mode: 'file', file: null, body: '' });
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    documentsApi.policy(id).then((x) => { if (!cancelled) setD(x); }, (err) => { if (!cancelled) setError(err.message); });
    return () => { cancelled = true; };
  }, [id]);

  const act = async (fn, done) => {
    setBusy(true); setError(''); setMsg('');
    try { const r = await fn(); if (r && r.id) setD(r); onChanged(); done?.(r); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };

  const deptName = (ids) => (ids ? ids.map((x) => departments.find((y) => y.id === x)?.name || `#${x}`).join(', ') : 'Everyone');
  const people = d ? [...d.people].sort((a, b) => (a.acknowledged_at ? 1 : 0) - (b.acknowledged_at ? 1 : 0) || a.name.localeCompare(b.name)) : [];

  return (
    <VaultModal title={d ? d.title : 'Document'} onClose={onClose} width={820}>
      {d && (
        <>
          <div className="pr-head" style={{ margin: '.3rem 0 .8rem' }}>
            <Pill value={d.status} />
            <span className="pr-sub">{d.category_label} · version {d.current_version} · for {deptName(d.departments)}
              {d.review_by ? ` · review by ${fmtDate(d.review_by)}` : ''}</span>
            {d.review_by && <ExpiryPill state={d.review_state} daysLeft={Math.round((new Date(`${d.review_by}T00:00:00`) - new Date()) / 86400000)} />}
          </div>
          {d.description && <p className="pr-sub" style={{ marginTop: 0 }}>{d.description}</p>}
          <div className="pr-tabs">
            {d.requires_ack && <button type="button" className={`pr-tab ${tab === 'people' ? 'active' : ''}`} onClick={() => setTab('people')}>Acknowledgement ({d.acknowledged}/{d.audience})</button>}
            <button type="button" className={`pr-tab ${tab === 'versions' || (!d.requires_ack && tab === 'people') ? 'active' : ''}`} onClick={() => setTab('versions')}>Versions ({d.versions.length})</button>
            {manage && <button type="button" className={`pr-tab ${tab === 'new' ? 'active' : ''}`} onClick={() => setTab('new')}>Publish new version</button>}
            {manage && <button type="button" className={`pr-tab ${tab === 'settings' ? 'active' : ''}`} onClick={() => setTab('settings')}>Settings</button>}
          </div>
          {error && <div className="v-banner bad"><AlertCircle size={14} /><span>{error}</span></div>}
          {msg && <div className="v-banner ok"><span>{msg}</span></div>}

          {tab === 'people' && d.requires_ack && (
            <>
              <div className="pr-head" style={{ marginBottom: '.6rem' }}>
                <div className="doc-progress" style={{ flex: 1 }}><div style={{ width: `${d.audience ? (d.acknowledged / d.audience) * 100 : 0}%` }} /></div>
                <span className="pr-sub">{d.pending} pending</span>
                {manage && d.pending > 0 && (
                  <button type="button" className="v-btn" disabled={busy}
                    onClick={() => act(() => documentsApi.remindPolicy(d.id), (r) => setMsg(`Reminded ${r.reminded} people.`))}>
                    <BellRing size={13} /> Remind pending
                  </button>
                )}
              </div>
              <div className="ct-table-wrap"><table className="ct-table" style={{ minWidth: 0 }}>
                <thead><tr><th>Person</th><th>Acknowledged version {d.current_version}</th></tr></thead>
                <tbody>{people.map((p) => (
                  <tr key={p.user_id}><td className="strong">{p.name}<div className="ct-sub">{p.employee_code || ''}</div></td>
                    <td>{p.acknowledged_at ? fmtDateTime(p.acknowledged_at) : <span className="pr-status pending">Pending</span>}</td></tr>
                ))}</tbody>
              </table></div>
            </>
          )}

          {(tab === 'versions' || (!d.requires_ack && tab === 'people')) && (
            <div className="pr-timeline">
              {d.versions.map((v) => (
                <div key={v.version} className={`pr-rev ${v.version === d.current_version ? 'current' : ''}`}>
                  <div className="pr-rev-head">
                    <b>Version {v.version}</b>
                    <span className="pr-sub">{fmtDateTime(v.published_at)}{v.published_by ? ` · ${v.published_by}` : ''}</span>
                    {d.requires_ack && <span className="v-chip">{v.acknowledged} acknowledged</span>}
                    <button type="button" className="v-btn" onClick={() => act(() => documentsApi.downloadPolicy(d.id, v.version))}>
                      <Download size={12} /> {v.file_name ? `${v.file_name} ${fmtSize(v.size)}` : 'Text'}
                    </button>
                  </div>
                  {v.change_note && <div className="pr-sub">{v.change_note}</div>}
                </div>
              ))}
            </div>
          )}

          {tab === 'new' && manage && (
            <form onSubmit={(e) => {
              e.preventDefault();
              act(() => documentsApi.newPolicyVersion(d.id, { change_note: note, body: content.mode === 'text' ? content.body : null },
                content.mode === 'file' ? content.file : null), () => { setNote(''); setTab('versions'); setMsg('New version published.'); });
            }}>
              <label className="pr-field" style={{ marginBottom: '.6rem' }}><span>What changed — shown to everyone</span>
                <input required minLength={3} maxLength={255} value={note} onChange={(e) => setNote(e.target.value)} /></label>
              <Content value={content} onChange={setContent} />
              {d.requires_ack && <p className="pr-sub">Everyone it is for will be asked to acknowledge the new version.</p>}
              <div className="pr-actions"><button type="submit" className="pr-btn-primary" disabled={busy}><Upload size={14} /> Publish version {d.current_version + 1}</button></div>
            </form>
          )}

          {tab === 'settings' && manage && <Settings d={d} departments={departments} busy={busy}
            save={(body) => act(() => documentsApi.editPolicy(d.id, body), () => setMsg('Saved.'))} />}

          <div className="pr-actions" style={{ justifyContent: 'flex-start' }}>
            <AccessLogButton targetType="hr_document" targetId={d.id} title={d.title} />
          </div>
        </>
      )}
    </VaultModal>
  );
}

function Settings({ d, departments, busy, save }) {
  const [f, setF] = useState({ title: d.title, description: d.description || '', requires_ack: d.requires_ack,
    departments: d.departments || [], review_by: d.review_by || '', status: d.status });
  return (
    <form onSubmit={(e) => {
      e.preventDefault();
      save({ title: f.title, description: f.description, requires_ack: f.requires_ack, departments: f.departments,
        status: f.status, ...(f.review_by ? { review_by: f.review_by } : { clear_review_by: true }) });
    }}>
      <div className="pr-form three">
        <label className="pr-field" style={{ gridColumn: 'span 2' }}><span>Title</span>
          <input required value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></label>
        <label className="pr-field"><span>Status</span>
          <select value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>
            <option value="active">Published</option><option value="archived">Archived (hidden from staff)</option>
          </select></label>
        <label className="pr-field full"><span>Summary</span>
          <input value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></label>
        <label className="pr-field"><span>Review by</span>
          <input type="date" value={f.review_by} onChange={(e) => setF({ ...f, review_by: e.target.value })} /></label>
        <label className="pr-field" style={{ gridColumn: 'span 2' }}><span>Who it is for (none = everyone)</span>
          <select multiple value={f.departments.map(String)} style={{ height: 76 }}
            onChange={(e) => setF({ ...f, departments: [...e.target.selectedOptions].map((o) => Number(o.value)) })}>
            {departments.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
          </select></label>
        <label className="pr-check full"><input type="checkbox" checked={f.requires_ack} onChange={(e) => setF({ ...f, requires_ack: e.target.checked })} /> Requires acknowledgement</label>
      </div>
      <div className="pr-actions"><button type="submit" className="pr-btn-primary" disabled={busy}>Save</button></div>
    </form>
  );
}

export default function Policies() {
  const { user } = useAuth();
  const { can } = usePermissions();
  const [rows, setRows] = useState(null);
  const [departments, setDepartments] = useState([]);
  const [error, setError] = useState('');
  const [creating, setCreating] = useState(false);
  const [open, setOpen] = useState(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    Promise.all([documentsApi.policies(), documentsApi.departments()]).then(
      ([p, d]) => { if (!cancelled) { setRows(p); setDepartments(d); } },
      (err) => { if (!cancelled) setError(err.message); },
    );
    return () => { cancelled = true; };
  }, [tick]);

  return (
    <DashboardLayout title="Policies & Handbook" {...sidebarPropsFor(user)}>
      <div className="pr-head">
        <div>
          <h2>Policies &amp; handbook</h2>
          <div className="pr-sub">Each new version is kept, and asks for acknowledgement again when the document needs it.</div>
        </div>
        <span className="grow" />
        {can('documents.manage') && <button type="button" className="pr-btn-primary" onClick={() => setCreating(true)}><FilePlus2 size={14} /> Publish document</button>}
      </div>
      {error && <div className="v-banner bad"><AlertCircle size={14} /><span>{error}</span></div>}
      <div className="ct-table-wrap">
        <table className="ct-table">
          <thead><tr><th>Document</th><th>Type</th><th>Version</th><th>Acknowledged</th><th>Review</th><th>Status</th></tr></thead>
          <tbody>
            {!rows && !error && <tr><td colSpan={6} className="ct-empty">Loading…</td></tr>}
            {rows && rows.length === 0 && <tr><td colSpan={6} className="ct-empty">Nothing published yet. Start with your leave policy and handbook.</td></tr>}
            {(rows || []).map((d) => (
              <tr key={d.id} className="expandable" onClick={() => setOpen(d.id)}>
                <td className="strong">{d.title}{d.description && <div className="ct-sub">{d.description}</div>}</td>
                <td>{d.category_label}</td>
                <td className="mono">v{d.current_version}<div className="ct-sub">{fmtDate(d.published_at)}</div></td>
                <td>{d.requires_ack ? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem' }}>
                    <div className="doc-progress"><div style={{ width: `${d.audience ? (d.acknowledged / d.audience) * 100 : 0}%` }} /></div>
                    <span className="mono">{d.acknowledged}/{d.audience}</span>
                  </div>) : <span className="ct-sub">Not required</span>}</td>
                <td>{d.review_by ? <><div className="mono">{fmtDate(d.review_by)}</div>{d.review_state !== 'valid' && <ExpiryPill state={d.review_state} daysLeft={Math.round((new Date(`${d.review_by}T00:00:00`) - new Date()) / 86400000)} />}</> : '—'}</td>
                <td><Pill value={d.status} label={d.status === 'active' ? 'published' : d.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {creating && <Publish departments={departments} onClose={() => setCreating(false)}
        onDone={(d) => { setCreating(false); setTick((n) => n + 1); setOpen(d.id); }} />}
      {open && <Detail id={open} departments={departments} onClose={() => setOpen(null)} onChanged={() => setTick((n) => n + 1)} />}
    </DashboardLayout>
  );
}
