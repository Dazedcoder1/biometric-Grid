// src/pages/vault/AuditLog.jsx
//
// The audit log viewer, with filters, CSV export and chain verification.
//
// Denials are styled to stand out. A spike in them is what probing looks like,
// and surfacing that is most of the reason denied attempts are recorded at all.

import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertCircle, CheckCircle, Download, RefreshCw, ShieldCheck, ShieldAlert,
} from 'lucide-react';

import DashboardLayout from '../../layouts/DashboardLayout';
import { useAuth } from '../../context/AuthContext';
import { vaultApi } from '../../services/api';
import { sidebarPropsFor } from '../../utils/sidebarRole';

const PAGE = 100;

export default function AuditLog() {
  const { user } = useAuth();
  const [entries, setEntries] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [actions, setActions] = useState([]);
  const [summary, setSummary] = useState(null);
  const [integrity, setIntegrity] = useState(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState('');

  const [filters, setFilters] = useState({
    action: '', result: '', actor_id: '', since: '', until: '',
  });

  const load = useCallback(async (nextOffset = 0) => {
    try {
      const data = await vaultApi.auditLog({
        ...filters, limit: PAGE, offset: nextOffset,
      });
      setEntries(data.entries);
      setTotal(data.total);
      setOffset(nextOffset);
    } catch (err) {
      setError(err.message);
    }
  }, [filters]);

  useEffect(() => {
    (async () => {
      try {
        const [a, s] = await Promise.all([
          vaultApi.auditActions(),
          vaultApi.auditSummary(7),
        ]);
        setActions(a);
        setSummary(s);
      } catch (err) {
        setError(err.message);
      }
    })();
  }, []);

  useEffect(() => { load(0); }, [load]);

  const verify = async () => {
    setChecking(true);
    setError('');
    try {
      setIntegrity(await vaultApi.auditIntegrity());
    } catch (err) {
      setError(err.message);
    } finally {
      setChecking(false);
    }
  };

  const exportCsv = async () => {
    try { await vaultApi.downloadAudit(filters); }
    catch (err) { setError(err.message); }
  };

  const set = (k, v) => setFilters((f) => ({ ...f, [k]: v }));

  return (
    <DashboardLayout title="Audit Log" {...sidebarPropsFor(user)}>
      <style>{`
        .al-bar { display:flex; gap:.5rem; flex-wrap:wrap; margin-bottom:1rem; }
        .al-btn { background:var(--bg3); border:1px solid var(--border);
          border-radius:8px; padding:.4rem .7rem; cursor:pointer;
          color:var(--text2); font-size:.8rem; display:inline-flex;
          align-items:center; gap:.35rem; }
        .al-btn:hover { background:var(--bg4); color:var(--text); }
        .al-row { display:grid; grid-template-columns:70px 150px 120px 1fr 90px;
          gap:.6rem; padding:.5rem .7rem; border-top:1px solid var(--border);
          font-size:.8rem; align-items:center; }
        .al-row.denied { background:rgba(239,68,68,.07); }
        .al-head { font-family:var(--mono); font-size:.68rem;
          text-transform:uppercase; opacity:.55; }
        .al-stat { flex:1; min-width:120px; padding:.7rem .9rem;
          background:var(--bg2); border:1px solid var(--border);
          border-radius:10px; }
      `}</style>

      {error && (
        <div style={{ padding: '.6rem .8rem', borderRadius: 8, marginBottom: '1rem',
          background: 'rgba(239,68,68,.12)', fontSize: '.85rem' }}>
          <AlertCircle size={13} style={{ verticalAlign: -2, marginRight: 6 }} />
          {error}
        </div>
      )}

      {/* ─── headline numbers ──────────────────────────────────────── */}
      {summary && (
        <div style={{ display: 'flex', gap: '.7rem', marginBottom: '1rem',
          flexWrap: 'wrap' }}>
          <div className="al-stat">
            <div className="al-head">Successful · {summary.days}d</div>
            <div style={{ fontSize: '1.3rem', fontWeight: 600 }}>
              {summary.success}
            </div>
          </div>
          <div className="al-stat" style={{
            borderColor: summary.denied > 0 ? 'rgba(239,68,68,.4)' : undefined }}>
            <div className="al-head">Denied</div>
            <div style={{ fontSize: '1.3rem', fontWeight: 600,
              color: summary.denied > 0 ? '#ef4444' : 'inherit' }}>
              {summary.denied}
            </div>
          </div>
          <div className="al-stat">
            <div className="al-head">Errors</div>
            <div style={{ fontSize: '1.3rem', fontWeight: 600 }}>
              {summary.errors}
            </div>
          </div>
        </div>
      )}

      {/* ─── integrity ─────────────────────────────────────────────── */}
      <div className="card-box" style={{ marginBottom: '1rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between',
          alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 220 }}>
            <h4 style={{ margin: '0 0 .25rem', fontSize: '.92rem' }}>
              Chain integrity
            </h4>
            {!integrity ? (
              <div style={{ fontSize: '.8rem', opacity: .7 }}>
                Every entry is hashed against the one before it. Run a check to
                confirm nothing has been altered or removed.
              </div>
            ) : (
              <>
                <div style={{ fontSize: '.85rem',
                  color: integrity.ok ? '#22c55e' : '#ef4444' }}>
                  {integrity.ok ? <ShieldCheck size={14} /> : <ShieldAlert size={14} />}
                  {' '}
                  {integrity.ok
                    ? `Verified ${integrity.checked} entries — chain intact.`
                    : `BROKEN at entry ${integrity.broken_at}: ${integrity.detail}`}
                </div>
                <div style={{ fontSize: '.72rem', opacity: .6, marginTop: '.35rem' }}>
                  {integrity.caveat}
                </div>
                {integrity.anchor && (
                  <div style={{ fontSize: '.68rem', opacity: .55,
                    fontFamily: 'var(--mono)', marginTop: '.3rem',
                    wordBreak: 'break-all' }}>
                    head: {integrity.anchor}
                  </div>
                )}
              </>
            )}
          </div>
          <button className="al-btn" onClick={verify} disabled={checking}>
            <RefreshCw size={13} /> {checking ? 'Checking…' : 'Verify chain'}
          </button>
        </div>
      </div>

      {/* ─── filters ───────────────────────────────────────────────── */}
      <div className="al-bar">
        <select className="form-input" value={filters.action}
          onChange={(e) => set('action', e.target.value)} style={{ minWidth: 190 }}>
          <option value="">All actions</option>
          {actions.map((a) => (
            <option key={a.action} value={a.action}>
              {a.label} ({a.count})
            </option>
          ))}
        </select>

        <select className="form-input" value={filters.result}
          onChange={(e) => set('result', e.target.value)}>
          <option value="">Any result</option>
          <option value="success">Success</option>
          <option value="denied">Denied</option>
          <option value="error">Error</option>
        </select>

        <input className="form-input" type="number" placeholder="Actor ID"
          value={filters.actor_id} onChange={(e) => set('actor_id', e.target.value)}
          style={{ width: 110 }} />

        <input className="form-input" type="date" value={filters.since}
          onChange={(e) => set('since', e.target.value)} />
        <input className="form-input" type="date" value={filters.until}
          onChange={(e) => set('until', e.target.value)} />

        <button className="al-btn" onClick={exportCsv}>
          <Download size={13} /> CSV
        </button>
      </div>

      {/* ─── entries ───────────────────────────────────────────────── */}
      <div className="card-box" style={{ padding: 0 }}>
        <div className="al-row al-head" style={{ borderTop: 'none' }}>
          <div>Seq</div><div>When</div><div>Actor</div><div>Action</div>
          <div>Result</div>
        </div>

        {entries.length === 0 ? (
          <div style={{ padding: '2rem', textAlign: 'center', opacity: .6,
            fontSize: '.85rem' }}>
            Nothing matches these filters.
          </div>
        ) : entries.map((e) => (
          <div key={e.seq}
            className={`al-row ${e.result === 'denied' ? 'denied' : ''}`}>
            <div style={{ fontFamily: 'var(--mono)', opacity: .6 }}>{e.seq}</div>
            <div style={{ fontSize: '.75rem' }}>
              {new Date(e.occurred_at).toLocaleString()}
            </div>
            <div style={{ fontSize: '.78rem' }}>
              {e.actor_id ? `#${e.actor_id}` : 'system'}
              {e.actor_role && (
                <span style={{ opacity: .55 }}> · {e.actor_role}</span>
              )}
            </div>
            <div>
              {e.label}
              {e.target_type && (
                <span style={{ opacity: .55, fontSize: '.75rem' }}>
                  {' '}· {e.target_type} {e.target_id}
                </span>
              )}
              {e.reason && (
                <div style={{ fontSize: '.72rem', opacity: .6 }}>{e.reason}</div>
              )}
            </div>
            <div style={{ fontSize: '.75rem',
              color: e.result === 'denied' ? '#ef4444'
                : e.result === 'error' ? '#f59e0b' : '#22c55e' }}>
              {e.result === 'success' && <CheckCircle size={11} />} {e.result}
            </div>
          </div>
        ))}
      </div>

      {total > PAGE && (
        <div style={{ display: 'flex', justifyContent: 'space-between',
          alignItems: 'center', marginTop: '.8rem', fontSize: '.8rem' }}>
          <button className="al-btn" disabled={offset === 0}
            onClick={() => load(Math.max(0, offset - PAGE))}>
            Previous
          </button>
          <span style={{ opacity: .65 }}>
            {offset + 1}–{Math.min(offset + PAGE, total)} of {total}
          </span>
          <button className="al-btn" disabled={offset + PAGE >= total}
            onClick={() => load(offset + PAGE)}>
            Next
          </button>
        </div>
      )}
    </DashboardLayout>
  );
}
