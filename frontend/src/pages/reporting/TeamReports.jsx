// src/pages/reporting/TeamReports.jsx
//
// What the team did on a day, and what they are carrying. One row per person:
// report status, hours (reported against signed-in time), open / blocked /
// overdue work and the summary. Opening a row shows their report next to the
// work assigned to them; from there a manager can review, send the report
// back, assign more work, or mark an item done or cancelled.

import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertCircle, AlertTriangle, CalendarClock, Check, ChevronDown, ChevronRight, ClipboardPlus,
  Lightbulb, RotateCcw, Undo2, X,
} from 'lucide-react';

import DashboardLayout from '../../layouts/DashboardLayout';
import VaultModal from '../../components/VaultModal';
import { useAuth } from '../../context/AuthContext';
import usePermissions from '../../hooks/usePermissions';
import { reportingApi } from '../../services/api';
import { sidebarPropsFor } from '../../utils/sidebarRole';
import '../vault/vault.css';
import '../payroll/payroll.css';
import '../../components/clock.css';
import './reporting.css';

const STATUS_LABEL = { not_started: 'Not started', in_progress: 'In progress', blocked: 'Blocked', done: 'Done', cancelled: 'Cancelled' };
const PRIORITY = { urgent: 'Urgent', high: 'High', medium: 'Medium', low: 'Low' };
const inputStyle = { height: 38, padding: '0 .7rem', borderRadius: 8, border: '1px solid var(--border2)', background: 'var(--bg2)', color: 'var(--text)' };

function isoOf(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
const todayIso = () => isoOf(new Date());
function plusDays(n) { const d = new Date(); d.setDate(d.getDate() + n); return isoOf(d); }
function endOfWeek() { const d = new Date(); d.setDate(d.getDate() + ((5 - d.getDay() + 7) % 7)); return isoOf(d); }
const fmtShort = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
const h1 = (n) => (Math.round(n * 10) / 10).toString();

function AssignModal({ people, presetUserId, onClose, onDone }) {
  const [f, setF] = useState({ user_id: presetUserId ? String(presetUserId) : '', title: '', details: '', priority: 'medium', due_date: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const save = async (e) => {
    e.preventDefault();
    setBusy(true); setError('');
    try {
      await reportingApi.assign({
        user_id: Number(f.user_id), title: f.title.trim(), details: f.details.trim() || null,
        priority: f.priority, due_date: f.due_date || null,
      });
      onDone();
    } catch (err) { setError(err.message); setBusy(false); }
  };
  return (
    <VaultModal title="Assign work" onClose={onClose} width={560}>
      <form style={{ marginTop: '.8rem' }} onSubmit={save}>
        <label className="rp-field" style={{ marginBottom: '.7rem' }}><span>Person</span>
          <select required value={f.user_id} onChange={(e) => set('user_id', e.target.value)}>
            <option value="">Choose…</option>
            {people.map((p) => <option key={p.id} value={p.id}>{p.name}{p.department ? ` — ${p.department}` : ''}</option>)}
          </select></label>
        <label className="rp-field" style={{ marginBottom: '.7rem' }}><span>What needs doing</span>
          <input required minLength={2} maxLength={200} value={f.title} placeholder="e.g. Write the onboarding guide" onChange={(e) => set('title', e.target.value)} /></label>
        <label className="rp-field" style={{ marginBottom: '.7rem' }}><span>Details</span>
          <textarea value={f.details} maxLength={2000} placeholder="Context, links, what done looks like" onChange={(e) => set('details', e.target.value)} /></label>
        <div className="rp-field" style={{ marginBottom: '.7rem' }}><span>Priority</span>
          <div className="md-seg" role="radiogroup" aria-label="Priority" style={{ marginBottom: 0 }}>
            {Object.entries(PRIORITY).map(([k, label]) => (
              <button key={k} type="button" role="radio" aria-checked={f.priority === k}
                className={f.priority === k ? `on ${k === 'urgent' ? 'blocked' : k === 'high' ? 'in_progress' : 'not_started'}` : ''}
                onClick={() => set('priority', k)}>{label}</button>
            ))}
          </div>
        </div>
        <div className="rp-field"><span>Due</span>
          <div style={{ display: 'flex', gap: '.4rem', flexWrap: 'wrap', alignItems: 'center' }}>
            {[['Today', todayIso()], ['Tomorrow', plusDays(1)], ['This Friday', endOfWeek()], ['In 2 weeks', plusDays(14)]].map(([label, v]) => (
              <button key={label} type="button" className={`v-btn ${f.due_date === v ? 'tr-chip-on' : ''}`} onClick={() => set('due_date', v)}>{label}</button>
            ))}
            <input type="date" value={f.due_date} min={todayIso()} onChange={(e) => set('due_date', e.target.value)} style={{ ...inputStyle, height: 34 }} aria-label="Due date" />
            {f.due_date && <button type="button" className="md-link" onClick={() => set('due_date', '')}>No due date</button>}
          </div>
        </div>
        {error && <div className="v-banner bad" style={{ marginTop: '.8rem' }}><AlertCircle size={14} /><span>{error}</span></div>}
        <div className="pr-actions">
          <button type="button" className="v-btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="pr-btn-primary" disabled={busy}><ClipboardPlus size={14} /> {busy ? 'Assigning…' : 'Assign'}</button>
        </div>
      </form>
    </VaultModal>
  );
}

function PersonDetail({ row, date, canManage, onChanged, onAssign }) {
  const r = row.report;
  const [items, setItems] = useState(null);
  const [note, setNote] = useState('');
  const [reopening, setReopening] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    reportingApi.teamItems(row.user_id, date).then((x) => { if (!cancelled) setItems(x); }, (err) => { if (!cancelled) setError(err.message); });
    return () => { cancelled = true; };
  }, [row.user_id, date, row.report?.status]);

  const act = async (key, fn) => {
    setBusy(key); setError('');
    try { await fn(); setNote(''); setReopening(false); onChanged(); }
    catch (err) { setError(err.message); }
    finally { setBusy(''); }
  };
  const setItemStatus = (it, status) => act(`i${it.id}`, async () => {
    await reportingApi.editAssignment(it.id, { status });
    setItems((xs) => xs.map((x) => (x.key === it.key ? { ...x, status } : x)));
  });

  const clockH = r?.clock_seconds ? r.clock_seconds / 3600 : 0;
  return (
    <div className="tr-detail">
      <div className="tr-col">
        <h4 className="md-sec">Report{r ? ` · ${h1(r.hours_total)}h` : ''}{clockH ? ` · signed in ${h1(clockH)}h` : ''}</h4>
        {!r && <div className="md-hint">No report for {fmtShort(date)} yet.</div>}
        {r && (
          <>
            {r.summary && <p className="tr-summary">{r.summary}</p>}
            {r.lines.map((l) => (
              <div key={l.id} className={`tr-line s-${l.status}`}>
                <span className={`md-pill ${l.status}`}>{STATUS_LABEL[l.status] || l.status}</span>
                <div className="tr-line-main">
                  <div className="tr-line-what">
                    {l.what}
                    {(l.assignment_id || l.task_id) && <span className={`md-kind ${l.task_id ? 'task' : 'assignment'}`}>{l.task_id ? 'Task' : 'Assigned'}</span>}
                  </div>
                  {l.note && <div className="tr-line-note">{l.note}</div>}
                </div>
                <span className="mono tr-line-h">{l.progress != null && l.status !== 'done' ? `${l.progress}% · ` : ''}{l.hours ? `${l.hours}h` : ''}</span>
              </div>
            ))}
            {r.blockers && (
              <div className="md-note-card warn" style={{ marginTop: '.6rem' }}><AlertTriangle size={15} />
                <div><b>Blockers</b><p>{r.blockers}</p></div></div>
            )}
            {r.tomorrow_plan && (
              <div className="md-note-card plan"><Lightbulb size={15} />
                <div><b>Plan for next day</b><p>{r.tomorrow_plan}</p></div></div>
            )}
            {r.reviewed_at && <p className="rp-sub">Reviewed by {r.reviewed_by}{r.review_note ? `: “${r.review_note}”` : '.'}</p>}
            {r.reopen_note && r.status === 'draft' && <p className="rp-sub">Sent back by {r.reopened_by}: “{r.reopen_note}”</p>}

            {canManage && r.status === 'submitted' && (
              <div className="tr-actions">
                <input value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} style={{ ...inputStyle, height: 34, flex: 1, minWidth: 200 }}
                  placeholder={reopening ? 'What should they change? (required)' : 'Feedback (optional)'} aria-label="Note" />
                {!reopening ? (
                  <>
                    {!r.reviewed_at && (
                      <button type="button" className="v-btn" disabled={!!busy} onClick={() => act('review', () => reportingApi.review(r.id, note))}>
                        <Check size={13} /> Mark reviewed
                      </button>
                    )}
                    <button type="button" className="v-btn" onClick={() => setReopening(true)}><Undo2 size={13} /> Send back</button>
                  </>
                ) : (
                  <>
                    <button type="button" className="pr-btn-primary" disabled={!!busy || note.trim().length < 3}
                      onClick={() => act('reopen', () => reportingApi.reopen(r.id, note.trim()))}><Undo2 size={13} /> Send back</button>
                    <button type="button" className="v-btn" onClick={() => setReopening(false)}>Cancel</button>
                  </>
                )}
              </div>
            )}
          </>
        )}
      </div>

      <div className="tr-col">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <h4 className="md-sec" style={{ flex: 1 }}>Assigned work</h4>
          {canManage && <button type="button" className="md-link" onClick={onAssign}><ClipboardPlus size={13} /> Assign</button>}
        </div>
        {!items && !error && <div className="rp-sub">Loading…</div>}
        {items && items.length === 0 && <div className="md-hint">Nothing assigned.</div>}
        {items && items.map((it) => (
          <div key={it.key} className={`tr-item ${it.overdue ? 'overdue' : ''}`}>
            <span className={`md-prio ${it.priority}`} />
            <div className="tr-item-main">
              <div className="tr-item-title">{it.title}</div>
              <div className="md-item-meta">
                <span className={`md-kind ${it.kind}`}>{it.kind === 'task' ? 'Task' : 'Assigned'}</span>
                <span className={`md-pill ${it.status}`}>{STATUS_LABEL[it.status]}</span>
                {it.progress > 0 && it.status !== 'done' && <span>{it.progress}%</span>}
                {it.due_date && <span className={it.overdue ? 'bad' : ''}><CalendarClock size={11} /> {it.overdue ? 'overdue ' : 'due '}{fmtShort(it.due_date)}</span>}
                {it.carried_days > 0 && it.status !== 'done' && <span className="carry"><RotateCcw size={10} /> day {it.carried_days + 1}</span>}
              </div>
            </div>
            {canManage && it.kind === 'assignment' && it.status !== 'done' && (
              <div className="tr-item-btns">
                <button type="button" className="md-x" title="Mark done" aria-label={`Mark ${it.title} done`} disabled={!!busy}
                  onClick={() => setItemStatus(it, 'done')}><Check size={13} /></button>
                <button type="button" className="md-x" title="Cancel this work" aria-label={`Cancel ${it.title}`} disabled={!!busy}
                  onClick={() => window.confirm(`Cancel “${it.title}”? It will disappear from ${row.name}'s list.`) && setItemStatus(it, 'cancelled')}><X size={13} /></button>
              </div>
            )}
          </div>
        ))}
        {error && <div className="v-banner bad" style={{ marginTop: '.5rem' }}><AlertCircle size={14} /><span>{error}</span></div>}
      </div>
    </div>
  );
}

export default function TeamReports() {
  const { user } = useAuth();
  const { can } = usePermissions();
  const canManage = can('report.manage');
  const [date, setDate] = useState(todayIso());
  const [data, setData] = useState(null);
  const [people, setPeople] = useState([]);
  const [error, setError] = useState('');
  const [assignFor, setAssignFor] = useState(null);        // null closed, 0 = choose, id = preset
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const [open, setOpen] = useState(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    reportingApi.teamReports(date).then((d) => { if (!cancelled) { setData(d); setError(''); } }, (err) => { if (!cancelled) setError(err.message); });
    return () => { cancelled = true; };
  }, [date, tick]);
  useEffect(() => { reportingApi.people().then(setPeople, () => {}); }, []);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data?.people || []).filter((r) => {
      if (q && !(r.name.toLowerCase().includes(q) || (r.department || '').toLowerCase().includes(q))) return false;
      if (filter === 'missing') return r.state === 'missing';
      if (filter === 'blocked') return r.has_blockers || r.work.blocked > 0;
      if (filter === 'review') return r.state === 'submitted' && !r.report?.reviewed_at;
      return true;
    });
  }, [data, query, filter]);
  const c = data?.counts || {};
  const refresh = () => setTick((n) => n + 1);

  const FILTERS = [['all', 'Everyone', c.people], ['review', 'To review', (c.submitted || 0) - (c.reviewed || 0)],
    ['blocked', 'Blocked', c.blocked], ['missing', 'Missing', c.missing]];

  return (
    <DashboardLayout title="Team Reports" {...sidebarPropsFor(user)}>
      <div className="rp-head">
        <div><h2>Team reports</h2><div className="rp-sub">Day-end reports, and the work each person is carrying.</div></div>
        <span className="grow" />
        <input type="date" value={date} max={todayIso()} onChange={(e) => { setDate(e.target.value); setOpen(null); }} aria-label="Day" style={inputStyle} />
        {canManage && <button type="button" className="pr-btn-primary" onClick={() => setAssignFor(0)}><ClipboardPlus size={14} /> Assign work</button>}
      </div>

      {data && (
        <div className="ct-tiles tr-tiles" style={{ marginBottom: '1rem' }}>
          <div className="ct-tile"><span>People</span><strong>{c.people || 0}</strong></div>
          <div className="ct-tile in"><span>Submitted</span><strong>{c.submitted || 0}</strong></div>
          <div className="ct-tile absent"><span>Missing</span><strong>{c.missing || 0}</strong></div>
          <div className="ct-tile"><span>Blocked</span><strong style={{ color: c.blocked ? 'var(--bad)' : undefined }}>{c.blocked || 0}</strong></div>
          <div className="ct-tile"><span>Filed late</span><strong>{c.late || 0}</strong></div>
        </div>
      )}

      <div className="ct-toolbar" style={{ flexWrap: 'wrap', gap: '.5rem' }}>
        <div className="md-seg" role="tablist" aria-label="Filter" style={{ marginBottom: 0 }}>
          {FILTERS.map(([k, label, n]) => (
            <button key={k} type="button" role="tab" aria-selected={filter === k} className={filter === k ? 'on in_progress' : ''} onClick={() => setFilter(k)}>
              {label}{n ? ` · ${n}` : ''}
            </button>
          ))}
        </div>
        <input type="search" placeholder="Search name or department" aria-label="Search" value={query} onChange={(e) => setQuery(e.target.value)}
          style={{ ...inputStyle, minWidth: 220 }} />
      </div>

      {error && <div className="v-banner bad"><AlertCircle size={14} /><span>{error}</span></div>}

      <div className="ct-table-wrap">
        <table className="ct-table">
          <thead><tr><th aria-label="expand" /><th>Person</th><th>Report</th><th>Hours</th><th>Work</th><th>Summary</th></tr></thead>
          <tbody>
            {!data && !error && <tr><td colSpan={6} className="ct-empty">Loading…</td></tr>}
            {data && rows.length === 0 && <tr><td colSpan={6} className="ct-empty">Nobody here.</td></tr>}
            {rows.map((row) => {
              const r = row.report;
              const isOpen = open === row.user_id;
              const clockH = r?.clock_seconds ? r.clock_seconds / 3600 : 0;
              return (
                <React.Fragment key={row.user_id}>
                  <tr className="expandable" onClick={() => setOpen(isOpen ? null : row.user_id)}>
                    <td style={{ width: 28 }}>{isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</td>
                    <td className="strong">{row.name}<div className="ct-sub">{row.department || '—'}</div></td>
                    <td>
                      {row.state === 'submitted' && <span className="md-pill done"><Check size={11} /> Submitted</span>}
                      {row.state === 'draft' && <span className="md-pill in_progress">Draft</span>}
                      {row.state === 'missing' && <span className="md-pill blocked">Missing</span>}
                      {r?.is_late && <span className="md-pill not_started" style={{ marginLeft: 4 }}>late</span>}
                      {r?.reviewed_at && <span className="md-pill reviewed" style={{ marginLeft: 4 }}>reviewed</span>}
                    </td>
                    <td className="mono tr-hours">
                      {r ? `${h1(r.hours_total)}h` : '—'}
                      {clockH > 0 && <div className="ct-sub">signed in {h1(clockH)}h</div>}
                    </td>
                    <td>
                      <div className="tr-work">
                        <span title="Open items">{row.work.open} open</span>
                        {row.work.blocked > 0 && <span className="bad" title="Blocked items">{row.work.blocked} blocked</span>}
                        {row.work.overdue > 0 && <span className="warn" title="Overdue items">{row.work.overdue} overdue</span>}
                        {row.has_blockers && row.work.blocked === 0 && <span className="bad"><AlertTriangle size={11} /> blockers</span>}
                      </div>
                    </td>
                    <td className="ct-sub" style={{ maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {r ? (r.summary || `${r.lines.length} line${r.lines.length === 1 ? '' : 's'}`) : ''}
                    </td>
                  </tr>
                  {isOpen && (
                    <tr className="detail"><td colSpan={6} style={{ padding: 0 }}>
                      <PersonDetail row={row} date={date} canManage={canManage} onChanged={refresh}
                        onAssign={() => setAssignFor(row.user_id)} />
                    </td></tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {assignFor !== null && (
        <AssignModal people={people} presetUserId={assignFor || null} onClose={() => setAssignFor(null)}
          onDone={() => { setAssignFor(null); refresh(); }} />
      )}
    </DashboardLayout>
  );
}
