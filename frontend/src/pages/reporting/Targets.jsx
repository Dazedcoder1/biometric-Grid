// src/pages/reporting/Targets.jsx
//
// Targets on a Gantt timeline. An employee sees their own; an admin sees
// everyone they oversee and can create targets (3-month, 6-month, anything)
// for a person or a department, with milestones. Everyone with access can
// track progress; owners and managing admins can update it.

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertCircle, BarChart3, Check, List, Pencil, Plus, Target as TargetIcon, Trash2,
} from 'lucide-react';

import DashboardLayout from '../../layouts/DashboardLayout';
import VaultModal from '../../components/VaultModal';
import { useAuth } from '../../context/AuthContext';
import usePermissions from '../../hooks/usePermissions';
import { reportingApi } from '../../services/api';
import { sidebarPropsFor } from '../../utils/sidebarRole';
import Gantt from './Gantt';
import '../vault/vault.css';
import '../payroll/payroll.css';
import '../../components/clock.css';
import './reporting.css';

const STATE_LABEL = {
  on_track: 'On track', at_risk: 'At risk', overdue: 'Overdue', done: 'Done',
  upcoming: 'Upcoming', cancelled: 'Cancelled',
};
const STATE_CLASS = { on_track: 'submitted', at_risk: 'draft', overdue: 'overdue', done: 'done', upcoming: 'reviewed', cancelled: 'missing' };

function fmtDate(iso) {
  return iso ? new Date(`${iso}T00:00:00`).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '—';
}

function TargetEditor({ people, departments, onClose, onDone }) {
  const [f, setF] = useState({ title: '', description: '', who: 'person', user_id: '', dept_id: '', start_date: '', end_date: '' });
  const [ms, setMs] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const quick = (months) => {
    const s = new Date();
    const e = new Date(); e.setMonth(e.getMonth() + months);
    const iso = (d) => d.toISOString().slice(0, 10);
    setF((x) => ({ ...x, start_date: iso(s), end_date: iso(e) }));
  };
  const save = async (e) => {
    e.preventDefault();
    setBusy(true); setError('');
    try {
      const body = {
        title: f.title, description: f.description || null,
        start_date: f.start_date, end_date: f.end_date,
        milestones: ms.filter((m) => m.title.trim()).map((m) => ({ title: m.title.trim(), due_date: m.due_date || null })),
        ...(f.who === 'person' ? { user_id: Number(f.user_id) } : { dept_id: Number(f.dept_id) }),
      };
      onDone(await reportingApi.createTarget(body));
    } catch (err) { setError(err.message); setBusy(false); }
  };
  return (
    <VaultModal title="New target" onClose={onClose} width={680}>
      <form onSubmit={save} style={{ marginTop: '.8rem' }}>
        <label className="rp-field" style={{ marginBottom: '.6rem' }}><span>Title</span>
          <input required minLength={2} maxLength={200} value={f.title} placeholder="Ship v2 of the platform" onChange={(e) => setF({ ...f, title: e.target.value })} /></label>
        <label className="rp-field" style={{ marginBottom: '.6rem' }}><span>Description</span>
          <textarea value={f.description} maxLength={5000} onChange={(e) => setF({ ...f, description: e.target.value })} /></label>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '.6rem' }}>
          <label className="rp-field"><span>For</span>
            <select value={f.who} onChange={(e) => setF({ ...f, who: e.target.value })}>
              <option value="person">A person</option>
              {departments.length > 0 && <option value="department">A department</option>}
            </select></label>
          {f.who === 'person' ? (
            <label className="rp-field"><span>Person</span>
              <select required value={f.user_id} onChange={(e) => setF({ ...f, user_id: e.target.value })}>
                <option value="">Choose…</option>
                {people.map((p) => <option key={p.id} value={p.id}>{p.name}{p.employee_code ? ` (${p.employee_code})` : ''}</option>)}
              </select></label>
          ) : (
            <label className="rp-field"><span>Department</span>
              <select required value={f.dept_id} onChange={(e) => setF({ ...f, dept_id: e.target.value })}>
                <option value="">Choose…</option>
                {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select></label>
          )}
          <label className="rp-field"><span>Start</span>
            <input type="date" required value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} /></label>
          <label className="rp-field"><span>End</span>
            <input type="date" required value={f.end_date} onChange={(e) => setF({ ...f, end_date: e.target.value })} /></label>
        </div>
        <div style={{ display: 'flex', gap: '.4rem', margin: '.5rem 0 1rem', flexWrap: 'wrap' }}>
          <span className="rp-sub" style={{ alignSelf: 'center' }}>Quick:</span>
          <button type="button" className="v-btn" onClick={() => quick(3)}>3 months</button>
          <button type="button" className="v-btn" onClick={() => quick(6)}>6 months</button>
          <button type="button" className="v-btn" onClick={() => quick(12)}>1 year</button>
        </div>

        <h4 style={{ margin: '0 0 .4rem', fontSize: '.88rem' }}>Milestones</h4>
        {ms.map((m, i) => (
          <div key={i} className="rp-line" style={{ gridTemplateColumns: '1fr 150px 32px' }}>
            <input value={m.title} maxLength={200} placeholder="Milestone" onChange={(e) => setMs((xs) => xs.map((x, j) => (j === i ? { ...x, title: e.target.value } : x)))} />
            <input type="date" value={m.due_date} onChange={(e) => setMs((xs) => xs.map((x, j) => (j === i ? { ...x, due_date: e.target.value } : x)))} />
            <button type="button" className="rp-icon-btn" onClick={() => setMs((xs) => xs.filter((_, j) => j !== i))}><Trash2 size={14} /></button>
          </div>
        ))}
        <button type="button" className="v-btn" onClick={() => setMs((xs) => [...xs, { title: '', due_date: '' }])}><Plus size={13} /> Add milestone</button>

        {error && <div className="v-banner bad" style={{ marginTop: '1rem' }}><AlertCircle size={14} /><span>{error}</span></div>}
        <div className="pr-actions">
          <button type="button" className="v-btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="pr-btn-primary" disabled={busy}><TargetIcon size={14} /> {busy ? 'Creating…' : 'Create target'}</button>
        </div>
      </form>
    </VaultModal>
  );
}

function TargetDetail({ id, onClose, onChanged }) {
  const [t, setT] = useState(null);
  const [error, setError] = useState('');
  const [progress, setProgress] = useState(0);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => reportingApi.target(id).then((x) => { setT(x); setProgress(x.progress); }, (err) => setError(err.message)), [id]);
  useEffect(() => { load(); }, [load]);

  const saveProgress = async () => {
    setBusy(true); setError('');
    try { await reportingApi.setProgress(id, progress, note); setNote(''); await load(); onChanged(); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };
  const toggleMs = async (m) => {
    try { await reportingApi.editMilestone(id, m.id, { done: !m.done }); await load(); onChanged(); }
    catch (err) { setError(err.message); }
  };

  return (
    <VaultModal title={t ? t.title : 'Target'} onClose={onClose} width={640}>
      {error && <div className="v-banner bad"><AlertCircle size={14} /><span>{error}</span></div>}
      {t && (
        <>
          <div className="tg-top" style={{ marginTop: '.3rem' }}>
            <span className={`rp-status ${STATE_CLASS[t.state]}`}>{STATE_LABEL[t.state]}</span>
            <span className="rp-sub">{t.scope === 'department' ? `Department: ${t.department}` : t.owner}</span>
            <span className="rp-sub">{fmtDate(t.start_date)} → {fmtDate(t.end_date)}</span>
          </div>
          {t.description && <p className="rp-sub" style={{ marginTop: '.5rem' }}>{t.description}</p>}

          <div className="tg-bar"><div style={{ width: `${t.progress}%`, background: 'var(--teal)' }} /></div>
          <div className="tg-meta">
            <span>Progress <b style={{ color: 'var(--text)' }}>{t.progress}%</b></span>
            <span>Expected by now: {t.expected}%</span>
            <span>Milestones {t.milestones_done}/{t.milestones_total}</span>
          </div>

          {t.milestones.length > 0 && (
            <div style={{ margin: '1rem 0' }}>
              <h4 style={{ margin: '0 0 .3rem', fontSize: '.88rem' }}>Milestones</h4>
              {t.milestones.map((m) => (
                <div key={m.id} className={`tg-ms-row ${m.done ? 'done' : ''}`}>
                  <button type="button" className={`tg-check ${m.done ? 'done' : ''}`} disabled={!t.can_manage && t.owner_id == null}
                    onClick={() => toggleMs(m)} aria-label={m.done ? 'Mark not done' : 'Mark done'}>
                    {m.done && <Check size={12} />}
                  </button>
                  <span style={{ flex: 1 }}>{m.title}</span>
                  {m.due_date && <span className="rp-sub">{fmtDate(m.due_date)}</span>}
                </div>
              ))}
            </div>
          )}

          {t.can_manage && (
            <div className="card-box" style={{ padding: '.9rem', marginBottom: 0, marginTop: '1rem' }}>
              <h4 style={{ margin: '0 0 .5rem', fontSize: '.88rem' }}>Update progress</h4>
              <div style={{ display: 'flex', gap: '.6rem', alignItems: 'center', flexWrap: 'wrap' }}>
                <input type="range" min="0" max="100" value={progress} onChange={(e) => setProgress(Number(e.target.value))} style={{ flex: 1, minWidth: 160 }} />
                <span className="mono" style={{ width: 44, textAlign: 'right' }}>{progress}%</span>
              </div>
              <input className="rp-field" style={{ width: '100%', height: 36, padding: '0 .6rem', borderRadius: 8, border: '1px solid var(--border2)', background: 'var(--bg2)', color: 'var(--text)', marginTop: '.5rem' }}
                placeholder="Note (optional)" value={note} maxLength={1000} onChange={(e) => setNote(e.target.value)} />
              <div className="pr-actions">
                <button type="button" className="pr-btn-primary" onClick={saveProgress} disabled={busy}>{busy ? 'Saving…' : 'Save progress'}</button>
              </div>
            </div>
          )}

          {t.history?.length > 0 && (
            <div style={{ marginTop: '1rem' }}>
              <h4 style={{ margin: '0 0 .3rem', fontSize: '.88rem' }}>History</h4>
              {t.history.slice(0, 8).map((h, i) => (
                <div key={i} className="rp-sub" style={{ padding: '.2rem 0' }}>
                  {h.progress != null && <b style={{ color: 'var(--text2)' }}>{h.progress}% </b>}
                  {h.note || 'progress updated'} · {h.by} · {new Date(h.at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </VaultModal>
  );
}

export default function Targets() {
  const { user } = useAuth();
  const { can } = usePermissions();
  const canManage = can('target.manage');
  const canViewAll = can('target.view');
  const [targets, setTargets] = useState(null);
  const [people, setPeople] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [view, setView] = useState('gantt');
  const [error, setError] = useState('');
  const [creating, setCreating] = useState(false);
  const [open, setOpen] = useState(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const fetchTargets = canViewAll ? reportingApi.targets() : reportingApi.myTargets();
    const extras = canManage ? [reportingApi.people(), reportingApi.departments()] : [Promise.resolve([]), Promise.resolve([])];
    Promise.all([fetchTargets, ...extras]).then(
      ([t, p, d]) => { if (!cancelled) { setTargets(t); setPeople(p); setDepartments(d); setError(''); } },
      (err) => { if (!cancelled) setError(err.message); },
    );
    return () => { cancelled = true; };
  }, [tick, canViewAll, canManage]);

  const changed = () => setTick((n) => n + 1);
  const list = useMemo(() => targets || [], [targets]);
  const counts = useMemo(() => ({
    total: list.length,
    at_risk: list.filter((t) => t.state === 'at_risk').length,
    overdue: list.filter((t) => t.state === 'overdue').length,
    done: list.filter((t) => t.state === 'done').length,
  }), [list]);

  return (
    <DashboardLayout title="Targets" {...sidebarPropsFor(user)}>
      <div className="rp-head">
        <div>
          <h2>Targets</h2>
          <div className="rp-sub">{canViewAll ? 'Targets across your team, on a timeline.' : 'Your targets and milestones.'}</div>
        </div>
        <span className="grow" />
        <div className="ot-viewtoggle" role="group" aria-label="View">
          <button type="button" className={view === 'gantt' ? 'active' : ''} onClick={() => setView('gantt')}><BarChart3 size={13} /> Gantt</button>
          <button type="button" className={view === 'list' ? 'active' : ''} onClick={() => setView('list')}><List size={13} /> List</button>
        </div>
        {canManage && <button type="button" className="pr-btn-primary" onClick={() => setCreating(true)}><Plus size={14} /> New target</button>}
      </div>

      {error && <div className="v-banner bad"><AlertCircle size={14} /><span>{error}</span></div>}

      {targets && list.length > 0 && (
        <div className="ct-tiles" style={{ marginBottom: '1rem' }}>
          <div className="ct-tile"><span>Targets</span><strong>{counts.total}</strong></div>
          <div className="ct-tile"><span>At risk</span><strong style={{ color: 'var(--warn)' }}>{counts.at_risk}</strong></div>
          <div className="ct-tile absent"><span>Overdue</span><strong>{counts.overdue}</strong></div>
          <div className="ct-tile in"><span>Done</span><strong>{counts.done}</strong></div>
        </div>
      )}

      {!targets && !error && <div className="ct-empty">Loading…</div>}
      {targets && list.length === 0 && (
        <div className="card-box"><div className="v-empty"><div className="v-empty-title">No targets yet</div>
          <p className="v-empty-body">{canManage ? 'Create a target for a person or a department to see it on the timeline.' : 'Targets assigned to you will appear here.'}</p></div></div>
      )}

      {targets && list.length > 0 && view === 'gantt' && <Gantt targets={list} onOpen={(t) => setOpen(t.id)} />}

      {targets && list.length > 0 && view === 'list' && list.map((t) => (
        <div key={t.id} className="tg-card" onClick={() => setOpen(t.id)} style={{ cursor: 'pointer' }}>
          <div className="tg-top">
            <span className={`rp-status ${STATE_CLASS[t.state]}`}>{STATE_LABEL[t.state]}</span>
            <h4>{t.title}</h4>
            <span className="rp-sub">· {t.scope === 'department' ? t.department : t.owner}</span>
            <span className="grow" />
            {t.can_manage && <Pencil size={13} style={{ color: 'var(--text3)' }} />}
          </div>
          <div className="tg-bar"><div style={{ width: `${t.progress}%`, background: t.state === 'overdue' ? 'var(--red)' : t.state === 'at_risk' ? 'var(--amber)' : t.state === 'done' ? 'var(--green)' : 'var(--teal)' }} /></div>
          <div className="tg-meta">
            <span>{t.progress}% · expected {t.expected}%</span>
            <span>{fmtDate(t.start_date)} → {fmtDate(t.end_date)}</span>
            {t.milestones_total > 0 && <span>Milestones {t.milestones_done}/{t.milestones_total}</span>}
          </div>
        </div>
      ))}

      {creating && <TargetEditor people={people} departments={departments} onClose={() => setCreating(false)}
        onDone={() => { setCreating(false); changed(); }} />}
      {open && <TargetDetail id={open} onClose={() => setOpen(null)} onChanged={changed} />}
    </DashboardLayout>
  );
}
