// src/pages/vault/AuditLog.jsx
//
// The audit log viewer, with filters, CSV export and chain verification.
//
// Denials are styled to stand out. A spike in them is what probing looks like,
// and surfacing that is most of the reason denied attempts are recorded at all.

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertCircle, Download, FileSearch, RefreshCw, ShieldAlert, ShieldCheck, X,
} from 'lucide-react';

import {
  activeFilterChips, categoryMeta, groupByDay, shortAgo, timeOfDay,
} from '../../utils/auditMeta';

import DashboardLayout from '../../layouts/DashboardLayout';
import usePermissions from '../../hooks/usePermissions';
import { useAuth } from '../../context/AuthContext';
import { vaultApi } from '../../services/api';
import { sidebarPropsFor } from '../../utils/sidebarRole';
import './vault.css';

const PAGE = 100;

const NO_FILTERS = { action: '', result: '', actor_id: '', since: '', until: '' };

const RESULT_TONE = { denied: 'var(--bad)', error: 'var(--warn)', success: 'var(--ok)' };

export default function AuditLog() {
  const { user } = useAuth();
  const { can } = usePermissions();
  const canVerify = can('audit.verify');
  const canExport = can('audit.view');
  const [entries, setEntries] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [actions, setActions] = useState([]);
  const [summary, setSummary] = useState(null);
  const [integrity, setIntegrity] = useState(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState('');

  const [filters, setFilters] = useState(NO_FILTERS);

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

  const hasFilters = Object.values(filters).some(Boolean);
  const chips = useMemo(() => activeFilterChips(filters, actions), [filters, actions]);
  const groups = useMemo(() => groupByDay(entries), [entries]);

  return (
    <DashboardLayout title="Audit Log" {...sidebarPropsFor(user)}>
      {error && (
        <div className="v-banner bad">
          <AlertCircle size={14} />
          <span>{error}</span>
        </div>
      )}

      {/* ─── headline numbers ──────────────────────────────────────── */}
      {summary && (
        <div className="v-stats">
          <div className="v-stat">
            <div className="v-stat-label">Successful · {summary.days}d</div>
            <div className="v-stat-value">{summary.success}</div>
          </div>
          <div className="v-stat" style={{
            borderColor: summary.denied > 0 ? 'rgba(239,68,68,.4)' : undefined }}>
            <div className="v-stat-label">Denied</div>
            <div className="v-stat-value"
              style={{ color: summary.denied > 0 ? '#f87171' : 'inherit' }}>
              {summary.denied}
            </div>
          </div>
          <div className="v-stat">
            <div className="v-stat-label">Errors</div>
            <div className="v-stat-value">{summary.errors}</div>
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
            {!canVerify ? (
              // Explained rather than hidden. The chain is the reason this log
              // is worth anything, and the person running an organisation
              // should know it exists even though they cannot run the check —
              // "you have no button" reads as a missing feature, which is the
              // wrong impression to leave about an integrity guarantee.
              <div style={{ fontSize: '.8rem', color: 'var(--text2)' }}>
                Every entry is hashed against the one before it, so an altered
                or deleted entry breaks the chain.
                <div style={{ fontSize: '.75rem', color: 'var(--text3)', marginTop: '.4rem' }}>
                  The check itself is run by the platform operator. It walks the
                  whole chain across every organisation, so its result would
                  reveal activity outside yours — which is why it needs the
                  <code style={{ margin: '0 .25rem' }}>audit.verify</code>
                  permission.
                </div>
              </div>
            ) : !integrity ? (
              <div style={{ fontSize: '.8rem', color: 'var(--text2)' }}>
                Every entry is hashed against the one before it. Run a check to
                confirm nothing has been altered or removed.
              </div>
            ) : (
              <>
                <div style={{ fontSize: '.85rem',
                  color: integrity.ok ? 'var(--ok)' : 'var(--bad)' }}>
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
          {canVerify && (
            <button type="button" className="v-btn" onClick={verify} disabled={checking}>
              <RefreshCw size={13} /> {checking ? 'Checking…' : 'Verify chain'}
            </button>
          )}
        </div>
      </div>

      {/* ─── filters ───────────────────────────────────────────────── */}
      <div className="v-filters">
        {/* Every control is labelled. Two bare date fields side by side give no
            clue which is the start and which the end. */}
        <select className="form-input form-select" value={filters.action}
          aria-label="Filter by action"
          onChange={(e) => set('action', e.target.value)} style={{ minWidth: 190 }}>
          <option value="">All actions</option>
          {actions.map((a) => (
            <option key={a.action} value={a.action}>
              {a.label} ({a.count})
            </option>
          ))}
        </select>

        <select className="form-input form-select" value={filters.result}
          aria-label="Filter by result"
          onChange={(e) => set('result', e.target.value)}>
          <option value="">Any result</option>
          <option value="success">Success</option>
          <option value="denied">Denied</option>
          <option value="error">Error</option>
        </select>

        <input className="form-input" type="number" placeholder="Actor ID"
          aria-label="Filter by actor ID"
          value={filters.actor_id} onChange={(e) => set('actor_id', e.target.value)} />

        <label className="v-field">
          <span>From</span>
          <input className="form-input" type="date" value={filters.since}
            onChange={(e) => set('since', e.target.value)} />
        </label>
        <label className="v-field">
          <span>To</span>
          <input className="form-input" type="date" value={filters.until}
            onChange={(e) => set('until', e.target.value)} />
        </label>

        {canExport && (
          <button type="button" className="v-btn" onClick={exportCsv}>
            <Download size={13} /> CSV
          </button>
        )}
      </div>

      {/* Which filters are on, and one click to drop each. The bar above shows
          the controls; it does not show at a glance that a date three weeks ago
          is still narrowing the results. */}
      {chips.length > 0 && (
        <div className="v-active-filters">
          {chips.map((c) => (
            <button key={c.key} type="button" className="v-chip v-chip-remove"
              onClick={() => set(c.key, '')}
              aria-label={`Remove filter: ${c.label}`}>
              {c.label} <X size={10} />
            </button>
          ))}
          <button type="button" className="v-btn"
            onClick={() => setFilters(NO_FILTERS)}>
            Clear all
          </button>
        </div>
      )}

      {/* ─── entries ───────────────────────────────────────────────── */}
      {entries.length === 0 ? (
        <div className="card-box">
          <div className="v-empty">
            <div className="v-empty-icon"><FileSearch size={22} strokeWidth={1.5} /></div>
            <div className="v-empty-title">
              {hasFilters ? 'Nothing matches these filters' : 'No activity recorded yet'}
            </div>
            <p className="v-empty-body">
              {hasFilters
                ? 'Try widening the date range, or clear the filters to see everything.'
                : 'Entries appear here as soon as anyone reveals, shares or '
                  + 'rotates a credential.'}
            </p>
          </div>
        </div>
      ) : (
        groups.map((group) => (
          <section key={group.key} className="v-day">
            <h4 className="v-day-head">
              <span>{group.heading}</span>
              <span className="v-day-count">
                {group.entries.length} {group.entries.length === 1 ? 'entry' : 'entries'}
              </span>
            </h4>

            <div className="card-box" style={{ padding: 0, overflow: 'hidden' }}>
              {group.entries.map((e) => <LogRow key={e.seq} entry={e} today={group.heading === 'Today'} />)}
            </div>
          </section>
        ))
      )}

      {total > PAGE && (
        <div style={{ display: 'flex', justifyContent: 'space-between',
          alignItems: 'center', marginTop: '.8rem', fontSize: '.8rem' }}>
          <button className="v-btn" disabled={offset === 0}
            onClick={() => load(Math.max(0, offset - PAGE))}>
            Previous
          </button>
          <span style={{ opacity: .65 }}>
            {offset + 1}–{Math.min(offset + PAGE, total)} of {total}
          </span>
          <button className="v-btn" disabled={offset + PAGE >= total}
            onClick={() => load(offset + PAGE)}>
            Next
          </button>
        </div>
      )}
    </DashboardLayout>
  );
}

// ─── one entry ───────────────────────────────────────────────────────────────

function LogRow({ entry, today }) {
  const { icon: CategoryIcon, label: categoryLabel, tint } = categoryMeta(entry.category);
  const denied = entry.result === 'denied';
  const tampered = entry.action === 'credential.tamper_detected';

  return (
    <div className={`v-log ${denied ? 'denied' : ''} ${tampered ? 'tampered' : ''}`}>
      <span className="v-log-icon" style={{ color: tint }} title={categoryLabel}>
        <CategoryIcon size={14} strokeWidth={1.75} />
      </span>

      <div className="v-log-body">
        <div className="v-log-line">
          {/* Who first, then what. The previous order led with the sequence
              number, which is the one column nobody scans for. */}
          <strong>{entry.actor_name || (entry.actor_id ? `User #${entry.actor_id}` : 'System')}</strong>
          {' '}
          <span style={{ color: denied || tampered ? 'var(--bad)' : 'inherit' }}>
            {entry.label}
          </span>
          {entry.target_type && (
            <span className="v-log-target">
              {' '}{entry.target_type} {entry.target_id}
            </span>
          )}
        </div>

        <div className="v-log-meta">
          {/* Exact timestamp on hover: the grouping makes the day obvious, so
              the row only needs the time — but an audit trail must still be
              able to give you the precise moment. */}
          <span title={new Date(entry.occurred_at).toLocaleString()}>
            {today ? shortAgo(entry.occurred_at) : timeOfDay(entry.occurred_at)}
          </span>
          {entry.actor_role && <span>{entry.actor_role}</span>}
          {entry.source_ip && <span>{entry.source_ip}</span>}
          {entry.mfa_method && <span>{entry.mfa_method}</span>}
          <span className="v-log-seq" title="Position in the hash chain">
            #{entry.seq}
          </span>
        </div>

        {entry.reason && <div className="v-log-reason">{entry.reason}</div>}
      </div>

      {entry.result !== 'success' && (
        <span className="v-chip" style={{ color: RESULT_TONE[entry.result] }}>
          {entry.result}
        </span>
      )}
    </div>
  );
}
