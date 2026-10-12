// src/pages/documents/MyDocuments.jsx
//
// My letters (download, confirm receipt), the policies and handbook I need to
// read and acknowledge, and the documents HR keeps on file for me.

import React, { useEffect, useState } from 'react';
import { AlertCircle, Check, Download, FileText, ShieldCheck } from 'lucide-react';

import DashboardLayout from '../../layouts/DashboardLayout';
import VaultModal from '../../components/VaultModal';
import { useAuth } from '../../context/AuthContext';
import { documentsApi } from '../../services/api';
import { sidebarPropsFor } from '../../utils/sidebarRole';
import { ExpiryPill, Pill } from './shared';
import { fmtDate, fmtDateTime } from '../../utils/docFormat';

function ReadPolicy({ p, onClose, onAcked }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [agree, setAgree] = useState(false);
  const ack = async () => {
    setBusy(true); setError('');
    try { const r = await documentsApi.acknowledgePolicy(p.id); onAcked(p.id, r.acknowledged_at); }
    catch (err) { setError(err.message); setBusy(false); }
  };
  return (
    <VaultModal title={p.title} onClose={onClose} width={780}>
      <p className="pr-sub" style={{ margin: '.3rem 0 .8rem' }}>
        {p.category_label} · version {p.version} · published {fmtDate(p.published_at)}
        {p.change_note ? ` · what changed: ${p.change_note}` : ''}
      </p>
      {p.body && <div className="doc-letter">{p.body}</div>}
      {p.has_file && (
        <button type="button" className="v-btn" style={{ marginTop: '.6rem' }}
          onClick={async () => { try { await documentsApi.downloadMyPolicy(p.id); } catch (err) { setError(err.message); } }}>
          <Download size={13} /> Open the document
        </button>
      )}
      {error && <div className="v-banner bad" style={{ marginTop: '1rem' }}><AlertCircle size={14} /><span>{error}</span></div>}
      {p.requires_ack && !p.acknowledged_at && (
        <>
          <label className="pr-check" style={{ marginTop: '1rem' }}>
            <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
            I have read and understood version {p.version} of this document.
          </label>
          <div className="pr-actions">
            <button type="button" className="pr-btn-primary" disabled={!agree || busy} onClick={ack}>
              <ShieldCheck size={14} /> {busy ? 'Recording…' : 'Acknowledge'}
            </button>
          </div>
        </>
      )}
      {p.acknowledged_at && <div className="v-banner ok" style={{ marginTop: '1rem' }}><Check size={14} /><span>You acknowledged this version on {fmtDateTime(p.acknowledged_at)}.</span></div>}
    </VaultModal>
  );
}

export default function MyDocuments() {
  const { user } = useAuth();
  const [tab, setTab] = useState('policies');
  const [letters, setLetters] = useState(null);
  const [policies, setPolicies] = useState(null);
  const [files, setFiles] = useState(null);
  const [reading, setReading] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    Promise.all([documentsApi.myLetters(), documentsApi.myPolicies(), documentsApi.myFiles()]).then(
      ([l, p, f]) => {
        if (cancelled) return;
        setLetters(l); setPolicies(p); setFiles(f);
        if (!p.some((x) => x.requires_ack && !x.acknowledged_at) && l.some((x) => x.status === 'issued' && !x.acknowledged_at)) setTab('letters');
      },
      (err) => { if (!cancelled) setError(err.message); },
    );
    return () => { cancelled = true; };
  }, []);

  const run = async (fn) => { setError(''); try { await fn(); } catch (err) { setError(err.message); } };
  const pendingPolicies = (policies || []).filter((p) => p.requires_ack && !p.acknowledged_at).length;
  const newLetters = (letters || []).filter((l) => l.status === 'issued' && !l.acknowledged_at).length;

  return (
    <DashboardLayout title="My Documents" {...sidebarPropsFor(user)}>
      {error && <div className="v-banner bad"><AlertCircle size={14} /><span>{error}</span></div>}
      <div className="pr-tabs">
        <button type="button" className={`pr-tab ${tab === 'policies' ? 'active' : ''}`} onClick={() => setTab('policies')}>
          Policies &amp; handbook{pendingPolicies ? ` (${pendingPolicies} to acknowledge)` : ''}</button>
        <button type="button" className={`pr-tab ${tab === 'letters' ? 'active' : ''}`} onClick={() => setTab('letters')}>
          My letters{newLetters ? ` (${newLetters} new)` : ''}</button>
        <button type="button" className={`pr-tab ${tab === 'files' ? 'active' : ''}`} onClick={() => setTab('files')}>My file</button>
      </div>

      {tab === 'policies' && (
        <div className="doc-card-list">
          {policies && policies.length === 0 && <p className="pr-sub">Nothing published yet.</p>}
          {(policies || []).map((p) => {
            const pending = p.requires_ack && !p.acknowledged_at;
            return (
              <div key={p.id} className={`doc-card ${pending ? 'pending' : ''}`}>
                <div className="doc-card-main">
                  <h4>{p.title}</h4>
                  <div className="pr-sub">{p.category_label} · version {p.version} · {fmtDate(p.published_at)}</div>
                  {p.description && <div className="pr-sub" style={{ marginTop: '.3rem' }}>{p.description}</div>}
                </div>
                <div className="doc-card-actions">
                  {pending ? <span className="pr-status pending">Please acknowledge</span>
                    : p.acknowledged_at ? <span className="pr-status paid">Acknowledged</span> : null}
                  <button type="button" className={pending ? 'pr-btn-primary' : 'v-btn'} onClick={() => setReading(p)}>
                    <FileText size={13} /> {pending ? 'Read & acknowledge' : 'Read'}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {tab === 'letters' && (
        <div className="ct-table-wrap">
          <table className="ct-table">
            <thead><tr><th>Letter</th><th>Reference</th><th>Date</th><th>Status</th><th aria-label="Actions" /></tr></thead>
            <tbody>
              {letters && letters.length === 0 && <tr><td colSpan={5} className="ct-empty">No letters yet.</td></tr>}
              {(letters || []).map((l) => (
                <tr key={l.id}>
                  <td className="strong">{l.subject}<div className="ct-sub">{l.kind_label}</div>
                    {l.status === 'revoked' && <div className="ct-sub">Withdrawn: {l.revoke_reason}</div>}</td>
                  <td className="mono">{l.reference_no}</td>
                  <td className="mono">{fmtDate(l.letter_date)}</td>
                  <td><Pill value={l.status} label={l.status === 'revoked' ? 'withdrawn' : l.acknowledged_at ? 'received' : 'new'} /></td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <button type="button" className="v-btn" onClick={() => run(() => documentsApi.downloadMyLetter(l.id))}><Download size={13} /> PDF</button>{' '}
                    {l.status === 'issued' && !l.acknowledged_at && (
                      <button type="button" className="v-btn" onClick={() => run(async () => {
                        const r = await documentsApi.acknowledgeLetter(l.id);
                        setLetters((list) => list.map((x) => (x.id === l.id ? { ...x, acknowledged_at: r.acknowledged_at } : x)));
                      })}><Check size={13} /> Confirm received</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'files' && (
        <div className="ct-table-wrap">
          <table className="ct-table">
            <thead><tr><th>Document</th><th>Number</th><th>Expires</th><th>Status</th><th aria-label="Download" /></tr></thead>
            <tbody>
              {files && files.length === 0 && <tr><td colSpan={5} className="ct-empty">HR has not filed any documents for you yet.</td></tr>}
              {(files || []).map((f) => (
                <tr key={f.id}>
                  <td className="strong">{f.title}<div className="ct-sub">{f.doc_type_label}</div></td>
                  <td className="mono">{f.number || '—'}</td>
                  <td className="mono">{f.expires_on ? fmtDate(f.expires_on) : '—'}</td>
                  <td><ExpiryPill state={f.expiry_state} daysLeft={f.days_left} /></td>
                  <td><button type="button" className="v-btn" onClick={() => run(() => documentsApi.downloadMyFile(f.id))}><Download size={13} /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {reading && (
        <ReadPolicy p={reading} onClose={() => setReading(null)}
          onAcked={(id, at) => {
            setPolicies((list) => list.map((x) => (x.id === id ? { ...x, acknowledged_at: at } : x)));
            setReading((r) => ({ ...r, acknowledged_at: at }));
          }} />
      )}
    </DashboardLayout>
  );
}
