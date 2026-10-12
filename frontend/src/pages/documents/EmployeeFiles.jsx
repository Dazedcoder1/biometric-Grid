// src/pages/documents/EmployeeFiles.jsx
//
// Each person's file: ID proofs, contracts, visas, certificates. Documents
// with an expiry date are reminded at 30 days, 7 days and on the day — to HR
// and to the person — and uploading the renewal starts the clock again. Every
// earlier upload is kept as a version.

import React, { useEffect, useMemo, useState } from 'react';
import { AlertCircle, Download, FilePlus2, RefreshCcw } from 'lucide-react';

import DashboardLayout from '../../layouts/DashboardLayout';
import VaultModal from '../../components/VaultModal';
import { useAuth } from '../../context/AuthContext';
import usePermissions from '../../hooks/usePermissions';
import { documentsApi } from '../../services/api';
import { sidebarPropsFor } from '../../utils/sidebarRole';
import { AccessLogButton, ExpiryPill, PersonSelect } from './shared';
import { fmtDate, fmtDateTime, fmtSize } from '../../utils/docFormat';

const TYPES = [
  ['id_proof', 'ID proof (Aadhaar, PAN, passport)'], ['passport', 'Passport'], ['visa', 'Visa / work permit'],
  ['contract', 'Employment contract'], ['nda', 'NDA'], ['certificate', 'Certificate'],
  ['education', 'Education record'], ['medical', 'Medical / fitness'],
  ['background_check', 'Background verification'], ['other', 'Other'],
];
const ACCEPT = '.pdf,.png,.jpg,.jpeg,.docx,.txt';

function AddFile({ people, onClose, onDone }) {
  const [f, setF] = useState({ user_id: '', doc_type: 'id_proof', title: '', number: '', issued_on: '', expires_on: '', notes: '' });
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const go = async (e) => {
    e.preventDefault();
    setBusy(true); setError('');
    try { onDone(await documentsApi.addFile(f, file)); } catch (err) { setError(err.message); setBusy(false); }
  };
  return (
    <VaultModal title="File a document" onClose={onClose} width={720}>
      <form onSubmit={go} style={{ marginTop: '.8rem' }}>
        <div className="pr-form three">
          <label className="pr-field" style={{ gridColumn: 'span 2' }}><span>Person</span>
            <PersonSelect people={people} value={f.user_id} required onChange={(v) => setF({ ...f, user_id: v })} /></label>
          <label className="pr-field"><span>Type</span>
            <select value={f.doc_type} onChange={(e) => setF({ ...f, doc_type: e.target.value })}>
              {TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
          <label className="pr-field" style={{ gridColumn: 'span 2' }}><span>Title</span>
            <input required minLength={2} maxLength={200} value={f.title} placeholder="Passport" onChange={(e) => setF({ ...f, title: e.target.value })} /></label>
          <label className="pr-field"><span>Number</span>
            <input maxLength={80} value={f.number} onChange={(e) => setF({ ...f, number: e.target.value })} /></label>
          <label className="pr-field"><span>Issued on</span>
            <input type="date" value={f.issued_on} onChange={(e) => setF({ ...f, issued_on: e.target.value })} /></label>
          <label className="pr-field"><span>Expires on</span>
            <input type="date" value={f.expires_on} onChange={(e) => setF({ ...f, expires_on: e.target.value })} />
            <small>Reminders at 30 and 7 days, and on the day.</small></label>
          <label className="pr-field"><span>File (up to 10 MB)</span>
            <input type="file" required accept={ACCEPT} onChange={(e) => setFile(e.target.files?.[0] || null)} style={{ height: 'auto', padding: '.5rem' }} /></label>
          <label className="pr-field full"><span>Notes</span>
            <input maxLength={500} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></label>
        </div>
        {error && <div className="v-banner bad" style={{ marginTop: '1rem' }}><AlertCircle size={14} /><span>{error}</span></div>}
        <div className="pr-actions">
          <button type="button" className="v-btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="pr-btn-primary" disabled={busy}><FilePlus2 size={14} /> {busy ? 'Uploading…' : 'File document'}</button>
        </div>
      </form>
    </VaultModal>
  );
}

function FileDetail({ id, onClose, onChanged }) {
  const { can } = usePermissions();
  const manage = can('documents.manage');
  const [d, setD] = useState(null);
  const [renew, setRenew] = useState(null);
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    documentsApi.file(id).then((x) => { if (!cancelled) setD(x); }, (err) => { if (!cancelled) setError(err.message); });
    return () => { cancelled = true; };
  }, [id]);

  const download = async (v) => { setError(''); try { await documentsApi.downloadFileVersion(d.id, v); } catch (err) { setError(err.message); } };

  const submitRenewal = async (e) => {
    e.preventDefault();
    setBusy(true); setError('');
    try {
      await documentsApi.renewFile(d.id, renew, file);
      setD(await documentsApi.file(d.id));
      setRenew(null); setFile(null); onChanged();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };

  return (
    <VaultModal title={d ? `${d.title} — ${d.employee}` : 'Document'} onClose={onClose} width={720}>
      {d && (
        <>
          <div className="pr-head" style={{ margin: '.3rem 0 .8rem' }}>
            <ExpiryPill state={d.expiry_state} daysLeft={d.days_left} />
            <span className="pr-sub">{d.doc_type_label}{d.number ? ` · ${d.number}` : ''}
              {d.issued_on ? ` · issued ${fmtDate(d.issued_on)}` : ''}{d.expires_on ? ` · expires ${fmtDate(d.expires_on)}` : ''}</span>
          </div>
          {d.notes && <p className="pr-sub" style={{ marginTop: 0 }}>{d.notes}</p>}
          {error && <div className="v-banner bad"><AlertCircle size={14} /><span>{error}</span></div>}
          <h4 style={{ margin: '0 0 .5rem', fontSize: '.88rem' }}>Versions</h4>
          <div className="pr-timeline">
            {d.versions.map((v) => (
              <div key={v.version} className={`pr-rev ${v.version === d.version ? 'current' : ''}`}>
                <div className="pr-rev-head">
                  <b>Version {v.version}</b>
                  <span className="pr-sub">{fmtDateTime(v.created_at)}{v.created_by ? ` · ${v.created_by}` : ''}</span>
                  {v.expires_on && <span className="pr-sub">expires {fmtDate(v.expires_on)}</span>}
                  <button type="button" className="v-btn" onClick={() => download(v.version)}><Download size={12} /> {v.file_name} {fmtSize(v.size)}</button>
                </div>
                {v.note && <div className="pr-sub">{v.note}</div>}
              </div>
            ))}
          </div>
          {renew && (
            <form className="card-box" style={{ padding: '.9rem', marginBottom: 0 }} onSubmit={submitRenewal}>
              <div className="pr-form three">
                <label className="pr-field"><span>Renewed file</span>
                  <input type="file" required accept={ACCEPT} onChange={(e) => setFile(e.target.files?.[0] || null)} style={{ height: 'auto', padding: '.5rem' }} /></label>
                <label className="pr-field"><span>New expiry</span>
                  <input type="date" value={renew.expires_on} onChange={(e) => setRenew({ ...renew, expires_on: e.target.value })} /></label>
                <label className="pr-field"><span>Number (if changed)</span>
                  <input maxLength={80} value={renew.number} onChange={(e) => setRenew({ ...renew, number: e.target.value })} /></label>
                <label className="pr-field full"><span>Note</span>
                  <input maxLength={255} value={renew.note} onChange={(e) => setRenew({ ...renew, note: e.target.value })} /></label>
              </div>
              <div className="pr-actions">
                <button type="button" className="v-btn" onClick={() => setRenew(null)}>Cancel</button>
                <button type="submit" className="pr-btn-primary" disabled={busy}>Upload renewal</button>
              </div>
            </form>
          )}
          <div className="pr-actions" style={{ justifyContent: 'space-between' }}>
            <AccessLogButton targetType="employee_document" targetId={d.id} title={d.title} />
            {manage && !renew && (
              <button type="button" className="pr-btn-primary" onClick={() => setRenew({ expires_on: '', number: d.number || '', note: '' })}>
                <RefreshCcw size={14} /> Upload renewal
              </button>
            )}
          </div>
        </>
      )}
    </VaultModal>
  );
}

export default function EmployeeFiles() {
  const { user } = useAuth();
  const { can } = usePermissions();
  const [rows, setRows] = useState(null);
  const [people, setPeople] = useState([]);
  const [expiring, setExpiring] = useState({ documents: [], policies: [] });
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [error, setError] = useState('');
  const [adding, setAdding] = useState(false);
  const [open, setOpen] = useState(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    Promise.all([documentsApi.files(), documentsApi.people(), documentsApi.expiring(60)]).then(
      ([f, p, x]) => { if (!cancelled) { setRows(f); setPeople(p); setExpiring(x); } },
      (err) => { if (!cancelled) setError(err.message); },
    );
    return () => { cancelled = true; };
  }, [tick]);

  const list = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (rows || []).filter((r) => (filter === 'all' || r.expiry_state === filter)
      && (!q || (r.employee || '').toLowerCase().includes(q) || r.title.toLowerCase().includes(q)));
  }, [rows, filter, query]);

  const count = (s) => (rows || []).filter((r) => r.expiry_state === s).length;

  return (
    <DashboardLayout title="Employee Documents" {...sidebarPropsFor(user)}>
      <div className="pr-head">
        <div>
          <h2>Employee documents</h2>
          <div className="pr-sub">ID proofs, contracts, visas and certificates, with reminders before they expire.</div>
        </div>
        <span className="grow" />
        {can('documents.manage') && <button type="button" className="pr-btn-primary" onClick={() => setAdding(true)}><FilePlus2 size={14} /> File a document</button>}
      </div>
      {error && <div className="v-banner bad"><AlertCircle size={14} /><span>{error}</span></div>}

      <div className="ct-tiles">
        <button type="button" className="ct-tile" style={{ textAlign: 'left', cursor: 'pointer' }} onClick={() => setFilter('all')}><span>Documents</span><strong>{(rows || []).length}</strong></button>
        <button type="button" className="ct-tile absent" style={{ textAlign: 'left', cursor: 'pointer' }} onClick={() => setFilter('expired')}><span>Expired</span><strong>{count('expired')}</strong></button>
        <button type="button" className="ct-tile" style={{ textAlign: 'left', cursor: 'pointer' }} onClick={() => setFilter('expiring')}><span>Expiring in 30 days</span><strong style={{ color: 'var(--warn)' }}>{count('expiring')}</strong></button>
        <div className="ct-tile"><span>Policies due for review</span><strong>{expiring.policies.length}</strong></div>
      </div>

      <div className="ct-toolbar">
        <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Show">
          <option value="all">All</option><option value="expired">Expired</option>
          <option value="expiring">Expiring soon</option><option value="valid">Valid</option><option value="none">No expiry</option>
        </select>
        <input type="search" placeholder="Search person or document" aria-label="Search" value={query} onChange={(e) => setQuery(e.target.value)}
          style={{ height: 38, padding: '0 .7rem', borderRadius: 8, border: '1px solid var(--border2)', background: 'var(--bg2)', color: 'var(--text)', minWidth: 240 }} />
      </div>

      <div className="ct-table-wrap">
        <table className="ct-table">
          <thead><tr><th>Person</th><th>Document</th><th>Number</th><th>Expires</th><th>Status</th><th>Version</th></tr></thead>
          <tbody>
            {!rows && !error && <tr><td colSpan={6} className="ct-empty">Loading…</td></tr>}
            {rows && list.length === 0 && <tr><td colSpan={6} className="ct-empty">Nothing here.</td></tr>}
            {list.map((r) => (
              <tr key={r.id} className="expandable" onClick={() => setOpen(r.id)}>
                <td className="strong">{r.employee}</td>
                <td>{r.title}<div className="ct-sub">{r.doc_type_label}</div></td>
                <td className="mono">{r.number || '—'}</td>
                <td className="mono">{r.expires_on ? fmtDate(r.expires_on) : '—'}</td>
                <td><ExpiryPill state={r.expiry_state} daysLeft={r.days_left} /></td>
                <td className="mono">v{r.version}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {adding && <AddFile people={people} onClose={() => setAdding(false)} onDone={() => { setAdding(false); setTick((n) => n + 1); }} />}
      {open && <FileDetail id={open} onClose={() => setOpen(null)} onChanged={() => setTick((n) => n + 1)} />}
    </DashboardLayout>
  );
}
