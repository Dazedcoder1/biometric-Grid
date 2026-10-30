// src/pages/reporting/MyDay.jsx
//
// The day-end report, in two panels:
//   left   everything assigned to me — work my manager set in Reporting and my
//          open Task Manager tasks — with priority, due date and carry-over
//   right  the report: each picked item with status, hours, % and a note,
//          other work, a summary, blockers and tomorrow's plan
// A week strip switches days (missed days can be filed late); the hours meter
// compares what I report with my signed-in time from the Sign In/Out clock.

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertCircle, AlertTriangle, CalendarClock, Check, Clock, ExternalLink, Inbox, Lightbulb,
  ListPlus, MessageSquareWarning, Plus, RotateCcw, Send, Trash2, X,
} from 'lucide-react';

import DashboardLayout from '../../layouts/DashboardLayout';
import { useAuth } from '../../context/AuthContext';
import { reportingApi } from '../../services/api';
import { sidebarPropsFor } from '../../utils/sidebarRole';
import '../vault/vault.css';
import '../payroll/payroll.css';
import '../../components/clock.css';
import './reporting.css';

const STATUSES = [['not_started', 'Not started'], ['in_progress', 'In progress'], ['blocked', 'Blocked'], ['done', 'Done']];
const STATUS_LABEL = Object.fromEntries(STATUSES);
const PRIORITY = { urgent: 'Urgent', high: 'High', medium: 'Medium', low: 'Low' };

const parse = (iso) => new Date(`${iso}T00:00:00`);
const fmtLong = (iso) => parse(iso).toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' });
const fmtShort = (iso) => parse(iso).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' });
const daysBetween = (a, b) => Math.round((parse(b) - parse(a)) / 86400000);
const num = (v) => (v === '' || v == null ? 0 : Number(v) || 0);
const h1 = (n) => (Math.round(n * 10) / 10).toString();

function dueLabel(it, day) {
  if (!it.due_date) return null;
  const d = daysBetween(day, it.due_date);
  if (it.overdue) return `Overdue ${-d}d`;
  if (d === 0) return 'Due today';
  if (d === 1) return 'Due tomorrow';
  return `Due ${fmtShort(it.due_date)}`;
}

function StatusPill({ status }) {
  return <span className={`md-pill ${status}`}>{STATUS_LABEL[status] || status}</span>;
}

function AssignedCard({ it, day, picked, editable, open, onToggle, onAdd }) {
  const due = dueLabel(it, day);
  return (
    <div className={`md-item ${it.overdue ? 'overdue' : ''} ${picked ? 'picked' : ''} ${it.status === 'done' ? 'finished' : ''}`}>
      <span className={`md-prio ${it.priority}`} title={`${PRIORITY[it.priority] || it.priority} priority`} />
      <div className="md-item-body">
        <button type="button" className="md-item-top" onClick={onToggle} aria-expanded={open}>
          <span className="md-item-title">{it.title}</span>
          <StatusPill status={it.status} />
        </button>
        <div className="md-item-meta">
          <span className={`md-kind ${it.kind}`}>{it.kind === 'task' ? 'Task' : 'Assigned'}</span>
          <span className={`md-prio-label ${it.priority}`}>{PRIORITY[it.priority]}</span>
          {due && <span className={it.overdue ? 'bad' : ''}><CalendarClock size={12} /> {due}</span>}
          {it.assigned_by && <span>from {it.assigned_by}</span>}
          {it.carried_days > 0 && it.status !== 'done' && (
            <span className="carry" title={`On your list since ${fmtShort(it.since)}`}><RotateCcw size={11} /> day {it.carried_days + 1}</span>
          )}
        </div>
        {it.progress > 0 && it.status !== 'done' && (
          <div className="md-mini" title={`${it.progress}% complete`}><div style={{ width: `${it.progress}%` }} /></div>
        )}
        {open && (
          <div className="md-item-more">
            {it.details ? <p>{it.details}</p> : <p className="rp-sub">No further details.</p>}
            {it.url && <a href={it.url} target="_blank" rel="noreferrer" className="md-link"><ExternalLink size={12} /> Open the issue</a>}
          </div>
        )}
        {editable && (picked
          ? <span className="md-added"><Check size={12} /> In your report</span>
          : <button type="button" className="md-add" onClick={onAdd}><Plus size={13} /> Report on this</button>)}
      </div>
    </div>
  );
}

function ItemEditor({ it, v, editable, onChange, onRemove }) {
  return (
    <div className={`md-edit s-${v.status}`}>
      <div className="md-edit-top">
        <span className={`md-prio ${it.priority}`} />
        <b>{it.title}</b>
        <span className={`md-kind ${it.kind}`}>{it.kind === 'task' ? 'Task' : 'Assigned'}</span>
        {editable && (
          <button type="button" className="md-x" aria-label={`Remove ${it.title} from the report`} onClick={onRemove}><X size={14} /></button>
        )}
      </div>
      <div className="md-seg" role="radiogroup" aria-label="Status">
        {STATUSES.map(([k, label]) => (
          <button key={k} type="button" role="radio" aria-checked={v.status === k} disabled={!editable}
            className={v.status === k ? `on ${k}` : ''} onClick={() => onChange('status', k)}>{label}</button>
        ))}
      </div>
      <div className="md-edit-row">
        <label className="md-hours" title="Hours spent today">
          <Clock size={13} />
          <input type="number" min="0" max="24" step="0.25" value={v.hours} placeholder="0" disabled={!editable}
            aria-label="Hours" onChange={(e) => onChange('hours', e.target.value)} />
          <span>h</span>
        </label>
        {v.status === 'done' ? (
          <span className="md-complete"><Check size={13} /> Complete</span>
        ) : (
          <label className="md-prog">
            <input type="range" min="0" max="100" step="5" value={v.progress || 0} disabled={!editable}
              aria-label="Percent complete" onChange={(e) => onChange('progress', Number(e.target.value))} />
            <span className="mono">{v.progress || 0}%</span>
          </label>
        )}
      </div>
      <input className={`md-note ${v.status === 'blocked' && !v.note.trim() ? 'need' : ''}`} value={v.note} maxLength={500}
        disabled={!editable} aria-label="Note"
        placeholder={v.status === 'blocked' ? 'What is blocking you? (required)' : 'Note — what you did, what is left (optional)'}
        onChange={(e) => onChange('note', e.target.value)} />
    </div>
  );
}

function HoursMeter({ reported, clockSeconds, target }) {
  const clock = clockSeconds ? clockSeconds / 3600 : 0;
  const scale = Math.max(target, reported, clock, 1);
  const gap = clock > 0 ? reported - clock : 0;
  const flagged = clock > 0 && reported > 0 && Math.abs(gap) > 1.5 && Math.abs(gap) > clock * 0.25;
  return (
    <div className="md-meter">
      <div className="md-meter-nums">
        <div><b>{h1(reported)}h</b><span>reported</span></div>
        <div><b>{clock ? `${h1(clock)}h` : '—'}</b><span>signed in</span></div>
        <div><b>{h1(target)}h</b><span>work day</span></div>
      </div>
      <div className="md-meter-bar" aria-hidden="true">
        <div className="fill" style={{ width: `${(reported / scale) * 100}%` }} />
        {clock > 0 && <div className="clock" style={{ left: `${(clock / scale) * 100}%` }} title="Signed-in time" />}
        <div className="target" style={{ left: `${(target / scale) * 100}%` }} title="Work day" />
      </div>
      {flagged && (
        <div className="md-meter-warn"><AlertTriangle size={12} />
          {gap > 0 ? `${h1(gap)}h more than you were signed in` : `${h1(-gap)}h less than you were signed in`}
        </div>
      )}
    </div>
  );
}

export default function MyDay() {
  const { user } = useAuth();
  const [date, setDate] = useState(null);                 // null = today
  const [data, setData] = useState(null);
  const [targets, setTargets] = useState([]);
  const [summary, setSummary] = useState('');
  const [blockers, setBlockers] = useState('');
  const [plan, setPlan] = useState('');
  const [picked, setPicked] = useState({});               // item key -> { status, hours, progress, note }
  const [order, setOrder] = useState([]);
  const [others, setOthers] = useState([]);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [flash, setFlash] = useState('');
  const [openKey, setOpenKey] = useState(null);

  const hydrate = useCallback((d) => {
    setData(d);
    const r = d.report;
    setSummary(r?.summary || '');
    setBlockers(r?.blockers || '');
    setPlan(r?.tomorrow_plan || '');
    const p = {};
    const o = [];
    d.items.forEach((it) => {
      if (it.reported) {
        p[it.key] = {
          status: it.reported.status, hours: it.reported.hours || '',
          progress: it.reported.progress ?? it.progress, note: it.reported.note || '',
        };
        o.push(it.key);
      }
    });
    setPicked(p);
    setOrder(o);
    setOthers((d.other_lines || []).map((l) => ({ what: l.what, hours: l.hours || '', status: l.status, target_id: l.target_id })));
    setDirty(false);
  }, []);

  const load = useCallback((d) => reportingApi.day(d).then(hydrate, (err) => setError(err.message)), [hydrate]);
  useEffect(() => { load(date); }, [date, load]);
  useEffect(() => { reportingApi.myTargets().then(setTargets, () => {}); }, []);

  const items = useMemo(() => data?.items || [], [data]);
  const byKey = useMemo(() => Object.fromEntries(items.map((i) => [i.key, i])), [items]);
  const editable = !!data?.editable;
  const submitted = data?.report?.status === 'submitted';
  const touch = () => { setDirty(true); setFlash(''); };

  const addItem = (it) => {
    setPicked((p) => (p[it.key] ? p : {
      ...p,
      [it.key]: { status: it.status === 'not_started' ? 'in_progress' : it.status, hours: '', progress: it.progress || 0, note: '' },
    }));
    setOrder((o) => (o.includes(it.key) ? o : [...o, it.key]));
    touch();
  };
  const addAll = () => items.filter((i) => i.status !== 'done' && !picked[i.key]).forEach(addItem);
  const removeItem = (key) => {
    setPicked((p) => { const n = { ...p }; delete n[key]; return n; });
    setOrder((o) => o.filter((k) => k !== key));
    touch();
  };
  const setItem = (key, k, v) => { setPicked((p) => ({ ...p, [key]: { ...p[key], [k]: v } })); touch(); };
  const setOther = (i, k, v) => { setOthers((ls) => ls.map((l, j) => (j === i ? { ...l, [k]: v } : l))); touch(); };

  const totalHours = order.reduce((n, k) => n + num(picked[k]?.hours), 0) + others.reduce((n, l) => n + num(l.hours), 0);
  const unpicked = items.filter((i) => i.status !== 'done' && !picked[i.key]).length;
  const openCount = items.filter((i) => i.status !== 'done').length;

  const payload = () => ({
    summary, blockers, tomorrow_plan: plan,
    lines: [
      ...order.filter((k) => byKey[k]).map((k) => {
        const it = byKey[k];
        const v = picked[k];
        return {
          what: it.title.slice(0, 500),
          [it.kind === 'task' ? 'task_id' : 'assignment_id']: it.id,
          status: v.status,
          hours: v.hours === '' ? null : Number(v.hours),
          progress: v.status === 'done' ? 100 : Number(v.progress) || 0,
          note: v.note.trim() || null,
        };
      }),
      ...others.filter((l) => l.what.trim()).map((l) => ({
        what: l.what.trim(), hours: l.hours === '' ? null : Number(l.hours),
        status: l.status, target_id: l.target_id || null,
      })),
    ],
  });

  const go = (d) => {
    if (dirty && !window.confirm('You have unsaved changes. Leave this day without saving?')) return;
    setError(''); setFlash('');
    setDate(d === data?.today ? null : d);
  };

  const save = async () => {
    setBusy('save'); setError(''); setFlash('');
    try { await reportingApi.saveMyReport(data.date, payload()); await load(date); setFlash('Draft saved.'); }
    catch (err) { setError(err.message); }
    finally { setBusy(''); }
  };

  const submit = async () => {
    const missing = order.find((k) => picked[k]?.status === 'blocked' && !picked[k].note.trim());
    if (missing) { setError(`Say what is blocking “${byKey[missing]?.title}” before submitting.`); return; }
    setBusy('submit'); setError(''); setFlash('');
    try {
      await reportingApi.saveMyReport(data.date, payload());
      await reportingApi.submitMyReport(data.date);
      await load(date);
      setFlash(data.late ? 'Submitted (marked late).' : 'Submitted. Nice work today.');
    } catch (err) { setError(err.message); }
    finally { setBusy(''); }
  };

  if (!data) {
    return (
      <DashboardLayout title="My Day" {...sidebarPropsFor(user)}>
        {error ? <div className="v-banner bad"><AlertCircle size={14} /><span>{error}</span></div> : <div className="ct-empty">Loading…</div>}
      </DashboardLayout>
    );
  }

  const r = data.report;
  return (
    <DashboardLayout title="My Day" {...sidebarPropsFor(user)}>
      {/* ── header: date, status, week strip, hours ───────────────────────── */}
      <div className="md-head">
        <div className="md-title">
          <div className="md-eyebrow">Day-end report</div>
          <h2>{data.is_today ? 'Today' : fmtLong(data.date)}{data.is_today && <small>{fmtLong(data.date)}</small>}</h2>
          <div className="md-badges">
            <span className={`md-pill ${submitted ? 'done' : r ? 'in_progress' : 'not_started'}`}>
              {submitted ? <><Check size={11} /> Submitted</> : r ? 'Draft' : 'Not started'}
            </span>
            {r?.is_late && <span className="md-pill blocked">Late</span>}
            {r?.reviewed_at && <span className="md-pill reviewed">Reviewed</span>}
            {dirty && <span className="md-unsaved">Unsaved changes</span>}
          </div>
        </div>

        <div className="md-week" role="tablist" aria-label="Last seven days">
          {data.week.map((w) => {
            const d = parse(w.date);
            const past = w.date < data.today;
            const cls = [
              'md-day', w.state,
              w.date === data.date ? 'on' : '',
              !w.working ? 'off' : '',
              past && w.working && w.state === 'missing' ? 'gap' : '',
            ].join(' ');
            return (
              <button key={w.date} type="button" role="tab" aria-selected={w.date === data.date} className={cls}
                onClick={() => go(w.date)}
                title={`${fmtShort(w.date)} — ${w.state === 'missing' ? 'no report' : w.state}${w.late ? ' (late)' : ''}`}>
                <span>{d.toLocaleDateString('en-IN', { weekday: 'short' })}</span>
                <b>{d.getDate()}</b>
                <i />
              </button>
            );
          })}
        </div>

        <HoursMeter reported={totalHours} clockSeconds={data.clock?.effective_seconds} target={data.min_working_hours} />
      </div>

      {/* ── notices ───────────────────────────────────────────────────────── */}
      {error && <div className="v-banner bad"><AlertCircle size={14} /><span>{error}</span></div>}
      {flash && <div className="v-banner ok"><Check size={14} /><span>{flash}</span></div>}
      {data.locked_reason && <div className="v-banner bad"><AlertCircle size={14} /><span>{data.locked_reason}</span></div>}
      {r?.reopen_note && !submitted && (
        <div className="md-note-card warn">
          <MessageSquareWarning size={16} />
          <div><b>Sent back by {r.reopened_by}</b><p>{r.reopen_note}</p></div>
        </div>
      )}
      {data.late && editable && (
        <div className="md-note-card muted"><CalendarClock size={16} />
          <div><b>Filing for a past day</b><p>This report will be marked late when you submit it.</p></div>
        </div>
      )}
      {data.plan_from_previous && (
        <div className="md-note-card plan">
          <Lightbulb size={16} />
          <div><b>Your plan, written {fmtShort(data.plan_from_previous.date)}</b><p>{data.plan_from_previous.text}</p></div>
        </div>
      )}

      <div className="md-grid">
        {/* ── left: assigned to me ─────────────────────────────────────────── */}
        <section className="md-panel">
          <header className="md-panel-head">
            <h3><Inbox size={16} /> Assigned to you</h3>
            <span className="md-count">{openCount} open</span>
            {editable && unpicked > 0 && (
              <button type="button" className="md-link" onClick={addAll}><ListPlus size={14} /> Add all</button>
            )}
          </header>
          {items.length === 0 ? (
            <div className="md-empty">
              <Inbox size={22} />
              <p>Nothing assigned to you right now.</p>
              <span>Work your manager assigns, and your Task Manager tasks, appear here.</span>
            </div>
          ) : items.map((it) => (
            <AssignedCard key={it.key} it={it} day={data.date} picked={!!picked[it.key]} editable={editable}
              open={openKey === it.key} onToggle={() => setOpenKey((k) => (k === it.key ? null : it.key))}
              onAdd={() => addItem(it)} />
          ))}
        </section>

        {/* ── right: the report ───────────────────────────────────────────── */}
        <section className="md-panel md-report">
          <header className="md-panel-head">
            <h3><Send size={15} /> Report</h3>
            <span className="md-count">{h1(totalHours)}h</span>
          </header>

          <h4 className="md-sec">Assigned work</h4>
          {order.length === 0 && (
            <div className="md-hint">{editable ? 'Pick items on the left to report on them.' : 'No assigned work reported.'}</div>
          )}
          {order.filter((k) => byKey[k]).map((k) => (
            <ItemEditor key={k} it={byKey[k]} v={picked[k]} editable={editable}
              onChange={(field, value) => setItem(k, field, value)} onRemove={() => removeItem(k)} />
          ))}

          <h4 className="md-sec">Other work</h4>
          {others.map((l, i) => (
            <div key={i} className="md-other">
              <input value={l.what} maxLength={500} placeholder="Meeting, support, review…" disabled={!editable}
                aria-label="What" onChange={(e) => setOther(i, 'what', e.target.value)} />
              <input type="number" min="0" max="24" step="0.25" value={l.hours} placeholder="h" disabled={!editable}
                aria-label="Hours" onChange={(e) => setOther(i, 'hours', e.target.value)} />
              <select value={l.target_id || ''} disabled={!editable} aria-label="Target"
                onChange={(e) => setOther(i, 'target_id', e.target.value ? Number(e.target.value) : null)}>
                <option value="">No target</option>
                {targets.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
              </select>
              {editable && (
                <button type="button" className="md-x" aria-label="Remove line"
                  onClick={() => { setOthers((ls) => ls.filter((_, j) => j !== i)); touch(); }}><Trash2 size={14} /></button>
              )}
            </div>
          ))}
          {editable && (
            <button type="button" className="md-link" onClick={() => { setOthers((ls) => [...ls, { what: '', hours: '', status: 'done', target_id: null }]); touch(); }}>
              <Plus size={13} /> Add other work
            </button>
          )}

          <label className="md-field">
            <span>Summary</span>
            <textarea value={summary} maxLength={5000} disabled={!editable} rows={3}
              placeholder="Two or three lines on the day."
              onChange={(e) => { setSummary(e.target.value); touch(); }} />
          </label>
          <div className="md-two">
            <label className="md-field">
              <span>Blockers</span>
              <textarea value={blockers} maxLength={3000} disabled={!editable} rows={3}
                placeholder="Anything stopping you? Your manager is told when you submit."
                onChange={(e) => { setBlockers(e.target.value); touch(); }} />
            </label>
            <label className="md-field">
              <span>Tomorrow&apos;s plan</span>
              <textarea value={plan} maxLength={3000} disabled={!editable} rows={3}
                placeholder="What you will pick up next. It is shown to you tomorrow."
                onChange={(e) => { setPlan(e.target.value); touch(); }} />
            </label>
          </div>

          {editable ? (
            <div className="md-actions">
              <span className="rp-sub">Total {h1(totalHours)}h</span>
              <span className="grow" />
              <button type="button" className="v-btn" onClick={save} disabled={!!busy}>{busy === 'save' ? 'Saving…' : 'Save draft'}</button>
              <button type="button" className="pr-btn-primary" onClick={submit} disabled={!!busy}>
                <Send size={14} /> {busy === 'submit' ? 'Submitting…' : 'Submit report'}
              </button>
            </div>
          ) : submitted ? (
            <div className="md-submitted">
              <Check size={14} />
              <div>
                Submitted{r.submitted_at ? ` at ${new Date(r.submitted_at).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' })}` : ''}.
                {r.reviewed_at
                  ? <> Reviewed by {r.reviewed_by}{r.review_note ? <>: <q>{r.review_note}</q></> : '.'}</>
                  : ' Your manager can send it back if something needs changing.'}
              </div>
            </div>
          ) : null}
        </section>
      </div>
    </DashboardLayout>
  );
}
