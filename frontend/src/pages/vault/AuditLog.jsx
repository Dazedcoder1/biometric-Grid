// src/pages/vault/AuditLog.jsx
//
// The audit log viewer, with filters, CSV export and chain verification.
//
// It records the whole app now, not just the vault — sign-ins, people,
// leave, devices, settings, tasks — and keeps itself current: the first
// page refreshes every 30 seconds while the tab is visible. Later pages do
// not, because new entries arriving would shift what is on them.
//
// What you see is scoped on the server: a Tenant Admin sees the whole
// organisation, an Org Admin their own department.
//
// Denials are styled to stand out. A spike in them is what probing looks like,
// and surfacing that is most of the reason denied attempts are recorded at all.

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertCircle, Building2, CalendarDays, CheckSquare, ClipboardList, Cpu, Download, FileSearch, FileText, IndianRupee,
  KeyRound, Layers, LogIn, RefreshCw, ShieldAlert, ShieldCheck, Siren, UserCog, X,
} from 'lucide-react';

import {
  activeFilterChips, actorText, categoryMeta, groupByDay, shortAgo,
  targetText, timeOfDay,
} from '../../utils/auditMeta';

import DashboardLayout from '../../layouts/DashboardLayout';
import usePermissions from '../../hooks/usePermissions';
import { useAuth } from '../../context/AuthContext';
import { getActingTenantId, getActingTenantName, vaultApi } from '../../services/api';
import { isSuperAdmin } from '../../utils/roles';
import { sidebarPropsFor } from '../../utils/sidebarRole';
import './vault.css';

const PAGE = 100;
const REFRESH_MS = 30_000;

const NO_FILTERS = {
  action: '', result: '', actor_id: '', since: '', until: '',
};

// The log is split by scenario: one tab per kind of activity, each with its
// own count, instead of one stream where a payroll approval sits between
// forty letter downloads. Names match LOGS in routes/vault/activity.py.
const LOGS = [
  { key: 'all', label: 'All activity', icon: Layers, about: 'Everything, newest first.' },
  { key: 'signins', label: 'Sign-ins', icon: LogIn, about: 'Sign-ins, failed attempts, sign-outs, password changes and authenticator use.' },
  { key: 'people', label: 'People', icon: UserCog, about: 'Accounts created and changed, departments, Org Admins, HR access and password resets.' },
  { key: 'attendance', label: 'Attendance & leave', icon: CalendarDays, about: 'Web sign-in clock, leave requests and decisions, holidays and office-hours settings.' },
  { key: 'payroll', label: 'Payroll', icon: IndianRupee, about: 'Pay components, salary revisions, payroll months, payslips and expense claims.' },
  { key: 'documents', label: 'HR documents', icon: FileText, about: 'Letters, templates, policies and acknowledgements, and employee documents.' },
  { key: 'reporting', label: 'Reports & targets', icon: ClipboardList, about: 'Day-end reports submitted and reviewed, work focus, and targets and their progress.' },
  { key: 'vault', label: 'Vault & access', icon: KeyRound, about: 'Credentials revealed, created, rotated and shared; systems and dependencies.' },
  { key: 'devices', label: 'Devices', icon: Cpu, about: 'Scanners registered, changed and sent commands.' },
  { key: 'tasks', label: 'Tasks', icon: CheckSquare, about: 'Tasks and GitHub repositories.' },
  { key: 'organisation', label: 'Organisation', icon: Building2, about: 'Organisation-level changes and audit exports.' },
  { key: 'security', label: 'Security alerts', icon: Siren, about: 'Anything refused or failed — denied access, failed sign-ins, errors and tampering. A spike here is what probing looks like.' },
];
const LOG_KEY = 'audit_log_tab';

function savedLog() {
  try { return localStorage.getItem(LOG_KEY) || 'all'; } catch { return 'all'; }
}

const RESULT_TONE = { denied: 'var(--bad)', error: 'var(--warn)', success: 'var(--ok)' };

export default function AuditLog() {
  const { user } = useAuth();
  const { can, grantsAll } = usePermissions();
  // A Super Admin reads one organisation — the one they are working in — or
  // all of them at once. With none chosen, it is all of them.
  const superAdmin = isSuperAdmin(user);
  const actingName = getActingTenantName();
  const hasOrg = !!getActingTenantId();
  const [allOrgs, setAllOrgs] = useState(() => superAdmin && !hasOrg);
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
  const [updatedAt, setUpdatedAt] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const [filters, setFilters] = useState(NO_FILTERS);
  const [log, setLog] = useState(savedLog);
  // all | changes | reads (views and downloads)
  const [kind, setKind] = useState('all');
  const scopeParams = useMemo(() => ({
    ...(log !== 'all' ? { log } : {}),
    ...(kind !== 'all' ? { kind } : {}),
    ...(allOrgs ? { all_orgs: 'true' } : {}),
  }), [log, kind, allOrgs]);

  const chooseLog = (key) => {
    setLog(key);
    // An action from another log would leave the new tab empty.
    setFilters((f) => ({ ...f, action: '' }));
    try { localStorage.setItem(LOG_KEY, key); } catch { /* not remembered */ }
  };

  const load = useCallback(async (nextOffset = 0) => {
    try {
      const data = await vaultApi.auditLog({
        ...filters, ...scopeParams, limit: PAGE, offset: nextOffset,
      });
      setEntries(data.entries);
      setTotal(data.total);
      setOffset(nextOffset);
      setUpdatedAt(Date.now());
      setError('');
    } catch (err) {
      setError(err.message);
    }
  }, [filters, scopeParams]);

  // The headline numbers and the action list move as new entries arrive —
  // a new kind of action should appear in the filter without a reload.
  const loadSideData = useCallback(async () => {
    try {
      const [a, s] = await Promise.all([vaultApi.auditActions(allOrgs), vaultApi.auditSummary(7, allOrgs)]);
      setActions(a);
      setSummary(s);
    } catch (err) {
      setError(err.message);
    }
  }, [allOrgs]);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    await Promise.all([load(offset), loadSideData()]);
    setRefreshing(false);
  }, [load, loadSideData, offset]);

  // First load, and again whenever the filters change. Written out with a
  // cancellation flag: changing a filter mid-request must not let the older,
  // slower response land on top of the newer one.
  useEffect(() => {
    let cancelled = false;
    Promise.all([vaultApi.auditActions(allOrgs), vaultApi.auditSummary(7, allOrgs)]).then(
      ([a, s]) => { if (!cancelled) { setActions(a); setSummary(s); } },
      (err) => { if (!cancelled) setError(err.message); },
    );
    return () => { cancelled = true; };
  }, [allOrgs]);

  useEffect(() => {
    let cancelled = false;
    vaultApi.auditLog({ ...filters, ...scopeParams, limit: PAGE, offset: 0 }).then(
      (data) => {
        if (cancelled) return;
        setEntries(data.entries);
        setTotal(data.total);
        setOffset(0);
        setUpdatedAt(Date.now());
        setError('');
      },
      (err) => { if (!cancelled) setError(err.message); },
    );
    return () => { cancelled = true; };
  }, [filters, scopeParams]);

  // Live: first page only, tab visible only. A hidden tab polling every 30
  // seconds all day is load nobody is looking at.
  useEffect(() => {
    if (offset !== 0) return undefined;
    const tick = () => {
      if (document.visibilityState === 'visible') { load(0); loadSideData(); }
    };
    const timer = setInterval(tick, REFRESH_MS);
    // Coming back to the tab: catch up straight away rather than on the
    // next tick.
    const onVisible = () => { if (document.visibilityState === 'visible') tick(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => { clearInterval(timer); document.removeEventListener('visibilitychange', onVisible); };
  }, [offset, load, loadSideData]);

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
    try { await vaultApi.downloadAudit({ ...filters, ...scopeParams }); }
    catch (err) { setError(err.message); }
  };

  const set = (k, v) => setFilters((f) => ({ ...f, [k]: v }));

  const hasFilters = Object.values(filters).some(Boolean);
  const chips = useMemo(() => activeFilterChips(filters, actions), [filters, actions]);
  const counts = useMemo(
    () => Object.fromEntries((summary?.logs || []).map((x) => [x.log, x.count])), [summary],
  );
  // Tabs with nothing in them this week stay out of the way, unless open.
  const tabs = LOGS.filter((t) => t.key === 'all' || t.key === 'security' || t.key === log || (counts[t.key] || 0) > 0);
  const current = LOGS.find((t) => t.key === log) || LOGS[0];
  const logActions = log === 'all' || log === 'security' ? actions : actions.filter((a) => a.log === log);
  const groups = useMemo(() => groupByDay(entries), [entries]);

  return (
    <DashboardLayout title="Audit Log" {...sidebarPropsFor(user)}>
      {error && (
        <div className="v-banner bad">
          <AlertCircle size={14} />
          <span>{error}</span>
        </div>
      )}

      {!grantsAll && user?.role && user.role !== 'tenant_admin' && (
        <div className="v-banner info">
          <Building2 size={14} />
          <span>
            Showing activity in your department: things done by its people, and
            things done to them, their credentials, leave, tasks and systems.
          </span>
        </div>
      )}

      <div className="v-toolbar">
        {superAdmin && hasOrg && (
          <select
            className="form-input form-select"
            aria-label="Which organisations"
            value={allOrgs ? 'all' : 'org'}
            onChange={(e) => setAllOrgs(e.target.value === 'all')}
            style={{ minWidth: 200, marginRight: 'auto' }}
          >
            <option value="org">{actingName || 'This organisation'}</option>
            <option value="all">All organisations</option>
          </select>
        )}
        {superAdmin && !hasOrg && (
          <span className="v-toolbar-scope">All organisations</span>
        )}
        {offset === 0 && (
          <span className="v-live" title="New entries appear every 30 seconds">
            <span className="v-live-dot" aria-hidden="true" /> Live
          </span>
        )}
        {updatedAt && <span>Updated {shortAgo(new Date(updatedAt).toISOString())}</span>}
        <button type="button" className="v-btn" onClick={refresh} disabled={refreshing}>
          <RefreshCw size={13} /> {refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {/* ─── one log per scenario ─────────────────────────────────── */}
      <div className="al-tabs" role="tablist" aria-label="Which log">
        {tabs.map((t) => {
          const Icon = t.icon;
          const n = t.key === 'all'
            ? (summary ? summary.success + summary.denied + summary.errors : null)
            : counts[t.key];
          return (
            <button key={t.key} type="button" role="tab" aria-selected={log === t.key}
              className={`al-tab ${log === t.key ? 'active' : ''} ${t.key === 'security' ? 'security' : ''}`}
              onClick={() => chooseLog(t.key)}>
              <Icon size={14} />
              <span>{t.label}</span>
              {n != null && <span className={`al-count ${t.key === 'security' && n > 0 ? 'hot' : ''}`}>{n}</span>}
            </button>
          );
        })}
      </div>

      <div className="al-head">
        <div>
          <h3>{current.label}</h3>
          <p>
            {current.about}
            {summary && current.key !== 'all' && counts[current.key] != null && (
              <span className="al-sub"> {counts[current.key]} in the last {summary.days} days · {total} matching now.</span>
            )}
          </p>
        </div>
        <div className="al-kind" role="group" aria-label="Show">
          {[['all', 'Everything'], ['changes', 'Changes'], ['reads', 'Views & downloads']].map(([k, l]) => (
            <button key={k} type="button" className={kind === k ? 'active' : ''} onClick={() => setKind(k)}>{l}</button>
          ))}
        </div>
      </div>

      {/* ─── filters ───────────────────────────────────────────────── */}
      <div className="v-filters">
        {/* Every control is labelled. Two bare date fields side by side give no
            clue which is the start and which the end. */}
        <select className="form-input form-select" value={filters.action}
          aria-label="Filter by action"
          onChange={(e) => set('action', e.target.value)} style={{ minWidth: 190 }}>
          <option value="">All actions{log !== 'all' ? ' in this log' : ''}</option>
          {logActions.map((a) => (
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
                : 'Entries appear here as people sign in, change records, handle '
                  + 'leave and devices, or use the vault.'}
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
              {group.entries.map((e) => <LogRow key={e.seq} entry={e} today={group.heading === 'Today'} showOrg={allOrgs} />)}
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
      {/* ─── integrity ─────────────────────────────────────────────── */}
      <div className="card-box" style={{ marginTop: '1.2rem', marginBottom: 0 }}>
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

    </DashboardLayout>
  );
}

// ─── one entry ───────────────────────────────────────────────────────────────

function LogRow({ entry, today, showOrg }) {
  const { icon: CategoryIcon, label: categoryLabel, tint } = categoryMeta(entry.category);
  const denied = entry.result === 'denied';
  const tampered = entry.action === 'credential.tamper_detected';

  return (
    <div className={`v-log ${denied ? 'denied' : ''} ${tampered ? 'tampered' : ''} ${entry.is_read ? 'read' : ''}`}>
      <span className="v-log-icon" style={{ color: tint }} title={categoryLabel}>
        <CategoryIcon size={14} strokeWidth={1.75} />
      </span>

      <div className="v-log-body">
        <div className="v-log-line">
          {/* Who first, then what. The previous order led with the sequence
              number, which is the one column nobody scans for. */}
          {showOrg && entry.organisation && (
            <span className="v-chip" style={{ marginRight: 6 }} title="Organisation">{entry.organisation}</span>
          )}
          <strong>{actorText(entry)}</strong>
          {' '}
          <span style={{ color: denied || tampered ? 'var(--bad)' : 'inherit' }}>
            {entry.label}
          </span>
          {targetText(entry) && (
            <span className="v-log-target" title={entry.target_type ? `${entry.target_type} ${entry.target_id ?? ''}` : undefined}>
              {' · '}{targetText(entry)}
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
