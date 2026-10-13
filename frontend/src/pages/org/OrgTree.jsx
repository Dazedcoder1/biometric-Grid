// src/pages/org/OrgTree.jsx
//
// The organisation hierarchy, from the database, for whoever is looking:
//
//   Super Admin           every organisation; each loads when expanded
//   Organisation Admin    their organisation
//   Department Admin      their department, and who they report to
//   Employee              themselves, and who they report to
//
// Clicking a person opens their details and whatever the viewer may do —
// reset their password, make them a Department or Organisation Admin, move
// them to another department. The server decides all of it; the buttons only
// appear where it would say yes. The tree reloads after every change and
// every minute, so additions, transfers and new admins show up on their own.

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertCircle, AlertTriangle, ArrowRightLeft, Building2, ChevronsDownUp, ChevronsUpDown, Copy, Crown,
  FolderPlus, KeyRound, Maximize2, Minus, Network, Plus, RefreshCw, Search, Shield, Users, ZoomIn, ZoomOut,
} from 'lucide-react';

import DashboardLayout from '../../layouts/DashboardLayout';
import VaultModal from '../../components/VaultModal';
import { useAuth } from '../../context/AuthContext';
import { accountsApi, orgTreeApi } from '../../services/api';
import { sidebarPropsFor } from '../../utils/sidebarRole';
import '../vault/vault.css';
import '../payroll/payroll.css';
import './orgtree.css';

const REFRESH_MS = 60_000;

function Avatar({ p, big }) {
  return <span className={`ot-avatar ${p.role} ${big ? 'big' : ''}`} aria-hidden="true">{p.initials}</span>;
}

function PersonCard({ p, onOpen, hit }) {
  return (
    <button type="button" className={`oc-person ${p.role} ${hit ? 'hit' : ''}`} data-person={p.id}
      onClick={() => onOpen(p)} title={`${p.name} — ${p.role_label}`}>
      <Avatar p={p} />
      <span className="oc-person-text">
        <span className="oc-person-name">{p.name}{p.is_me ? ' (you)' : ''}</span>
        <span className="oc-person-sub">
          {p.employee_code ? <span className="code">{p.employee_code}</span> : p.role_label}
          {p.is_hr && <span className="ot-role hr">HR</span>}
        </span>
      </span>
    </button>
  );
}

/** Employees reporting to one admin: a compact column, so a big team does not make the chart miles wide. */
function Team({ people, onOpen, hitId }) {
  if (!people.length) return <div className="oc-team-empty">No employees yet</div>;
  return (
    <div className="oc-team">
      {people.map((p) => (
        <button key={p.id} type="button" className={`oc-member ${hitId === p.id ? 'hit' : ''}`} data-person={p.id} onClick={() => onOpen(p)}>
          <Avatar p={p} />
          <span className="oc-person-text">
            <span className="oc-person-name">{p.name}{p.is_me ? ' (you)' : ''}</span>
            <span className="oc-person-sub">
              {p.employee_code ? <span className="code">{p.employee_code}</span> : 'Employee'}
              {p.is_hr && <span className="ot-role hr">HR</span>}
            </span>
          </span>
        </button>
      ))}
    </div>
  );
}

function Card({ kind, icon, title, sub, warnings = [], open, onToggle, hasChildren, actions }) {
  return (
    <div className={`oc-card ${kind}`}>
      <div className="oc-card-head">
        <span className={`ot-kind ${kind}`}>{icon}</span>
        <span className="oc-card-text">
          <span className="oc-card-title">{title}</span>
          {sub && <span className="oc-card-sub">{sub}</span>}
        </span>
      </div>
      {warnings.length > 0 && (
        <div className="oc-warns">{warnings.map((w) => <span key={w} className="ot-warn"><AlertTriangle size={10} /> {w}</span>)}</div>
      )}
      {actions && <div className="oc-card-actions">{actions}</div>}
      {hasChildren && (
        <button type="button" className="oc-toggle" onClick={onToggle} aria-expanded={open} aria-label={open ? 'Collapse' : 'Expand'}>
          {open ? <Minus size={12} /> : <Plus size={12} />}
        </button>
      )}
    </div>
  );
}

function DepartmentNode({ d, canManage, open, toggle, onOpen, onAssign, hitId }) {
  const [first, ...more] = d.admins;
  return (
    <>
      <Card kind="dept" icon={<Users size={15} />} title={d.name}
        sub={`${d.count} ${d.count === 1 ? 'person' : 'people'}`} warnings={d.warnings}
        open={open} onToggle={toggle} hasChildren={d.count > 0 || canManage}
        actions={canManage && d.is_active && (
          <button type="button" className="ot-mini" onClick={() => onAssign(d)}>
            <Shield size={11} /> {d.admins.length ? 'Replace admin' : 'Assign admin'}
          </button>
        )} />
      {open && (
        <ul>
          {first ? (
            <li>
              <PersonCard p={first} onOpen={onOpen} hit={hitId === first.id} />
              <Team people={d.employees} onOpen={onOpen} hitId={hitId} />
            </li>
          ) : (
            <li><Team people={d.employees} onOpen={onOpen} hitId={hitId} /></li>
          )}
          {more.map((p) => <li key={p.id}><PersonCard p={p} onOpen={onOpen} hit={hitId === p.id} /></li>)}
        </ul>
      )}
    </>
  );
}

function OrganisationNode({ org, isOpen, toggle, openSet, toggleSet, onOpen, onAddDept, onAssign, hitId }) {
  const loaded = org.departments !== undefined;
  const deptCount = org.departments_count ?? (loaded ? org.departments.length : 0);
  return (
    <>
      <Card kind="org" icon={<Building2 size={15} />} title={org.name}
        sub={`${org.count} people · ${deptCount} ${deptCount === 1 ? 'department' : 'departments'}`}
        warnings={org.warnings} open={isOpen} onToggle={toggle} hasChildren
        actions={org.can_manage && !org.partial && (
          <button type="button" className="ot-mini" onClick={() => onAddDept(org)}><FolderPlus size={11} /> Add department</button>
        )} />
      {isOpen && (
        <ul>
          {!loaded && <li><div className="oc-team-empty">Loading…</div></li>}
          {loaded && (org.admins.length ? org.admins : [null]).map((p, i) => (
            <li key={p ? `a${p.id}` : `noadmin${i}`}>
              <div className="oc-label"><Crown size={11} /> Organisation Admin</div>
              {p ? <PersonCard p={p} onOpen={onOpen} hit={hitId === p.id} /> : <div className="oc-team-empty">None assigned</div>}
            </li>
          ))}
          {loaded && org.departments.map((d) => (
            <li key={d.id}>
              <DepartmentNode d={d} canManage={org.can_manage} open={openSet.has(`d${d.id}`)}
                toggle={() => toggleSet(`d${d.id}`)} onOpen={onOpen} onAssign={onAssign} hitId={hitId} />
            </li>
          ))}
          {loaded && org.unassigned?.length > 0 && (
            <li>
              <Card kind="group" icon={<Users size={14} />} title="Not in a department" sub={`${org.unassigned.length}`}
                open={openSet.has(`u${org.id}`)} onToggle={() => toggleSet(`u${org.id}`)} hasChildren />
              {openSet.has(`u${org.id}`) && <ul><li><Team people={org.unassigned} onOpen={onOpen} hitId={hitId} /></li></ul>}
            </li>
          )}
        </ul>
      )}
    </>
  );
}

function AddDepartmentModal({ org, onClose, onDone }) {
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  return (
    <VaultModal title={`Add a department to ${org.name}`} onClose={onClose}>
      <form style={{ marginTop: '.8rem' }} onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true); setError('');
        try { await orgTreeApi.addDepartment(name, org.id); onDone(`Department ${name} added to ${org.name}.`); }
        catch (err) { setError(err.message); setBusy(false); }
      }}>
        <label className="pr-field"><span>Department name</span>
          <input autoFocus required minLength={2} maxLength={80} value={name} onChange={(e) => setName(e.target.value)} placeholder="Finance" /></label>
        {error && <div className="v-banner bad" style={{ marginTop: '.8rem' }}><AlertCircle size={14} /><span>{error}</span></div>}
        <div className="pr-actions">
          <button type="button" className="v-btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="pr-btn-primary" disabled={busy}><FolderPlus size={14} /> Add department</button>
        </div>
      </form>
    </VaultModal>
  );
}

function AssignAdminModal({ dept, onClose, onDone }) {
  const [userId, setUserId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const current = dept.admins.map((a) => a.name).join(', ');
  return (
    <VaultModal title={`Department Admin of ${dept.name}`} onClose={onClose}>
      <form style={{ marginTop: '.8rem' }} onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true); setError('');
        try { const r = await orgTreeApi.assignDepartmentAdmin(dept.id, Number(userId)); onDone(r.message); }
        catch (err) { setError(err.message); setBusy(false); }
      }}>
        <label className="pr-field"><span>Choose an employee of {dept.name}</span>
          <select required value={userId} onChange={(e) => setUserId(e.target.value)}>
            <option value="">Choose…</option>
            {dept.employees.map((c) => <option key={c.id} value={c.id}>{c.name}{c.employee_code ? ` (${c.employee_code})` : ''}</option>)}
          </select></label>
        {current && <p className="pr-sub">{current} will become an employee of {dept.name}. One admin per department.</p>}
        {dept.employees.length === 0 && <p className="pr-sub">Nobody to choose yet — move or add an employee to this department first.</p>}
        {error && <div className="v-banner bad" style={{ marginTop: '.8rem' }}><AlertCircle size={14} /><span>{error}</span></div>}
        <div className="pr-actions">
          <button type="button" className="v-btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="pr-btn-primary" disabled={busy || !userId}><Shield size={14} /> Make Department Admin</button>
        </div>
      </form>
    </VaultModal>
  );
}

function PersonPanel({ id, onClose, onChanged }) {
  const [p, setP] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [temp, setTemp] = useState(null);
  const [moveTo, setMoveTo] = useState('');
  const [msg, setMsg] = useState('');

  const load = useCallback(() => orgTreeApi.person(id).then(setP, (err) => setError(err.message)), [id]);
  useEffect(() => { load(); }, [load]);

  const run = async (label, fn) => {
    setBusy(label); setError(''); setMsg('');
    try { const r = await fn(); if (r?.message) setMsg(r.message); onChanged(r?.message); await load(); return r; }
    catch (err) { setError(err.message); return null; }
    finally { setBusy(''); }
  };

  const reset = async () => {
    if (!window.confirm(`Reset ${p.name}'s password?\n\nThey get a temporary password, are signed out everywhere, and must choose a new password at their next sign-in.`)) return;
    const r = await run('reset', () => accountsApi.resetPassword(p.id, null, p.tenant_id));
    if (r?.temporary_password) setTemp(r.temporary_password);
  };

  return (
    <VaultModal title={p ? p.name : 'Person'} onClose={onClose} width={620}>
      {error && <div className="v-banner bad"><AlertCircle size={14} /><span>{error}</span></div>}
      {p && (
        <>
          <div className="ot-profile-head">
            <Avatar p={p} big />
            <div>
              <div className="ot-name" style={{ fontSize: '1.05rem' }}>{p.name}</div>
              <div style={{ display: 'flex', gap: '.35rem', flexWrap: 'wrap', marginTop: '.2rem' }}>
                <span className={`ot-role ${p.role}`}>{p.role_label}</span>
                {p.is_hr && <span className="ot-role hr">HR</span>}
                {p.must_change_password && <span className="ot-warn">Must change password</span>}
              </div>
            </div>
          </div>
          <div className="pr-lines" style={{ paddingTop: 0 }}>
            <div>
              <div className="pr-line"><span>Employee ID</span><b>{p.employee_code || '—'}</b></div>
              <div className="pr-line"><span>Email</span><b style={{ fontFamily: 'inherit' }}>{p.email || '—'}</b></div>
              <div className="pr-line"><span>Organisation</span><b style={{ fontFamily: 'inherit' }}>{p.organisation || '—'}</b></div>
              <div className="pr-line"><span>Department</span><b style={{ fontFamily: 'inherit' }}>{p.department || '—'}</b></div>
              <div className="pr-line"><span>Fingerprint</span><b style={{ fontFamily: 'inherit' }}>{p.fingerprint_enrolled ? 'Enrolled' : 'Not enrolled'}</b></div>
            </div>
            <div>
              <h5>Reports to</h5>
              {p.reports_to.length === 0 && <div className="pr-line"><span>—</span></div>}
              {p.reports_to.map((r) => (
                <div key={r.id} className="pr-line"><span>{r.name}</span><b style={{ fontFamily: 'inherit', fontWeight: 500 }}>{r.role_label}</b></div>
              ))}
            </div>
          </div>

          {msg && <div className="v-banner ok"><span>{msg}</span></div>}
          {temp && (
            <div className="card-box" style={{ padding: '.9rem', margin: '.6rem 0' }}>
              <div className="pr-sub" style={{ marginBottom: '.4rem' }}>Temporary password — shown once. Give it to {p.name} privately; they must change it when they sign in.</div>
              <div style={{ display: 'flex', gap: '.5rem', alignItems: 'center' }}>
                <span className="ot-temp">{temp}</span>
                <button type="button" className="v-btn" onClick={() => navigator.clipboard?.writeText(temp)}><Copy size={13} /> Copy</button>
              </div>
            </div>
          )}

          <div className="pr-actions" style={{ justifyContent: 'flex-start', flexWrap: 'wrap' }}>
            {p.actions.reset_password && (
              <button type="button" className="pr-btn-primary" disabled={!!busy} onClick={reset}>
                <KeyRound size={14} /> {busy === 'reset' ? 'Resetting…' : 'Reset password'}
              </button>
            )}
            {p.actions.make_department_admin && p.role !== 'org_admin' && (
              <button type="button" className="v-btn" disabled={!!busy} onClick={() => {
                if (window.confirm(`Make ${p.name} the Department Admin of ${p.department}? The current one becomes an employee.`)) {
                  run('dept', () => orgTreeApi.assignDepartmentAdmin(p.dept_id, p.id));
                }
              }}><Shield size={13} /> Make Department Admin</button>
            )}
            {p.actions.make_organisation_admin && (
              <button type="button" className="v-btn" disabled={!!busy} onClick={() => {
                if (window.confirm(`Make ${p.name} the Organisation Admin of ${p.organisation}? The current one becomes an employee.`)) {
                  run('org', () => orgTreeApi.assignOrganisationAdmin(p.tenant_id, p.id));
                }
              }}><Crown size={13} /> Make Organisation Admin</button>
            )}
          </div>

          {p.actions.move && p.departments.length > 1 && (
            <form className="pr-actions" style={{ justifyContent: 'flex-start' }} onSubmit={(e) => {
              e.preventDefault();
              run('move', () => orgTreeApi.move(p.id, Number(moveTo)));
            }}>
              <select value={moveTo} required onChange={(e) => setMoveTo(e.target.value)}
                style={{ height: 36, borderRadius: 8, border: '1px solid var(--border2)', background: 'var(--bg2)', color: 'var(--text)', padding: '0 .6rem' }}>
                <option value="">Move to department…</option>
                {p.departments.filter((d) => d.id !== p.dept_id).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
              <button type="submit" className="v-btn" disabled={!moveTo || !!busy}><ArrowRightLeft size={13} /> Move</button>
            </form>
          )}
          {!p.actions.reset_password && !p.actions.move && !p.actions.make_department_admin && !p.actions.make_organisation_admin && (
            <p className="pr-sub">{p.is_me ? 'To change your own password, use Change Password.' : 'You can view this person; changes are made by their administrators.'}</p>
          )}
        </>
      )}
    </VaultModal>
  );
}

export default function OrgTree() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [orgDetail, setOrgDetail] = useState({});          // super admin: tenant id -> loaded organisation
  const [open, setOpen] = useState(() => new Set(['root']));
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [person, setPerson] = useState(null);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);
  const [hitId, setHitId] = useState(null);
  const [tick, setTick] = useState(0);
  const [zoom, setZoom] = useState(() => (typeof window !== 'undefined' && window.innerWidth < 700 ? 0.8 : 1));
  const [addingTo, setAddingTo] = useState(null);
  const [assigning, setAssigning] = useState(null);
  const openRef = useRef(open);
  useEffect(() => { openRef.current = open; }, [open]);

  const toggle = useCallback((key) => setOpen((s) => {
    const n = new Set(s);
    if (n.has(key)) n.delete(key); else n.add(key);
    return n;
  }), []);

  // The tree, and every organisation already expanded, re-read together.
  useEffect(() => {
    let cancelled = false;
    orgTreeApi.tree().then(async (t) => {
      if (cancelled) return;
      setData(t); setError('');
      if (t.scope === 'organisation' || t.scope === 'department') {
        setOpen((s) => new Set([...s, `o${t.root.id}`, ...t.root.departments.map((d) => `d${d.id}`)]));
      } else if (t.scope === 'self') {
        setOpen((s) => new Set([...s, `o${t.root.id}`, ...t.root.departments.map((d) => `d${d.id}`)]));
      } else if (t.scope === 'platform') {
        const ids = t.root.organisations.map((o) => o.id).filter((oid) => openRef.current.has(`o${oid}`));
        const loaded = await Promise.all(ids.map((oid) => orgTreeApi.organisation(oid).catch(() => null)));
        if (!cancelled) setOrgDetail((m) => ({ ...m, ...Object.fromEntries(ids.map((oid, i) => [oid, loaded[i]]).filter(([, v]) => v)) }));
      }
    }, (err) => { if (!cancelled) setError(err.message); });
    return () => { cancelled = true; };
  }, [tick]);

  useEffect(() => {
    const t = setInterval(() => { if (document.visibilityState === 'visible') setTick((n) => n + 1); }, REFRESH_MS);
    return () => clearInterval(t);
  }, []);

  const expandOrg = useCallback(async (oid) => {
    const key = `o${oid}`;
    const opening = !openRef.current.has(key);
    toggle(key);
    if (opening && data?.scope === 'platform') {
      try {
        const o = await orgTreeApi.organisation(oid);
        setOrgDetail((m) => ({ ...m, [oid]: o }));
        setOpen((st) => new Set([...st, ...o.departments.map((d) => `d${d.id}`)]));
      } catch (err) { setError(err.message); }
    }
  }, [data, toggle]);

  const changed = (m) => { if (m) setNotice(m); setTick((n) => n + 1); };

  // Search, debounced, within the viewer's scope (enforced by the server).
  useEffect(() => {
    const q = query.trim();
    if (!q) { const t = setTimeout(() => setResults(null), 0); return () => clearTimeout(t); }
    const t = setTimeout(() => {
      orgTreeApi.search(q).then(setResults, (err) => setError(err.message));
    }, 250);
    return () => clearTimeout(t);
  }, [query]);

  const reveal = async (p) => {
    setResults(null); setQuery('');
    setHitId(p.id);
    const keys = [];
    if (p.tenant_id) keys.push(`o${p.tenant_id}`);
    if (p.dept_id && p.role !== 'tenant_admin') keys.push(`d${p.dept_id}`);
    else if (!p.dept_id && p.role !== 'tenant_admin') keys.push(`u${p.tenant_id}`);
    setOpen((s) => new Set([...s, ...keys]));
    if (data?.scope === 'platform' && p.tenant_id && !orgDetail[p.tenant_id]) {
      try { const o = await orgTreeApi.organisation(p.tenant_id); setOrgDetail((m) => ({ ...m, [p.tenant_id]: o })); }
      catch { /* shown on expand */ }
    }
    setPerson(p.id);
  };

  // Bring a searched-for person into view once their branch has rendered.
  useEffect(() => {
    if (!hitId) return undefined;
    const t = setTimeout(() => {
      document.querySelector(`[data-person="${hitId}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
    }, 350);
    return () => clearTimeout(t);
  }, [hitId, orgDetail, open]);

  const orgs = useMemo(() => {
    if (!data) return [];
    if (data.scope === 'platform') return data.root.organisations.map((o) => ({ ...o, ...(orgDetail[o.id] || {}) }));
    return [data.root];
  }, [data, orgDetail]);

  // Keep the top of the tree centred as branches open and close — until the
  // person scrolls or drags the chart themselves, then leave it where they put it.
  const viewportRef = useRef(null);
  const userMoved = useRef(false);
  useEffect(() => {
    const v = viewportRef.current;
    if (!v || !data || userMoved.current) return undefined;
    const id = requestAnimationFrame(() => { v.scrollLeft = Math.max(0, (v.scrollWidth - v.clientWidth) / 2); });
    return () => cancelAnimationFrame(id);
  }, [data, orgDetail, open, zoom]);

  const expandAll = () => {
    const keys = ['root'];
    orgs.forEach((o) => {
      keys.push(`o${o.id}`);
      (o.departments || []).forEach((d) => keys.push(`d${d.id}`));
      if (o.unassigned?.length) keys.push(`u${o.id}`);
    });
    setOpen(new Set(keys));
  };

  const scopeText = {
    platform: 'Every organisation on the platform.',
    organisation: 'Your organisation: its admin, departments and people.',
    department: 'Your department, and who it reports to.',
    self: 'You, and who you report to.',
  }[data?.scope] || '';

  return (
    <DashboardLayout title="Organisation" {...sidebarPropsFor(user)}>
      <div className="ot-bar">
        <div>
          <h2 style={{ margin: 0, fontSize: '1.15rem' }}>Organisation</h2>
          <div className="pr-sub">{scopeText}</div>
        </div>
        <span className="grow" />
        {data && data.scope !== 'self' && (
          <div className="ot-search">
            <Search size={14} />
            <input type="search" placeholder="Search name, email or employee ID" aria-label="Search people"
              value={query} onChange={(e) => setQuery(e.target.value)} />
            {results && (
              <div className="ot-results">
                {results.length === 0 && <div className="ot-empty" style={{ padding: '.6rem' }}>Nobody found.</div>}
                {results.map((r) => (
                  <button key={r.id} type="button" className="ot-result" onClick={() => reveal(r)}>
                    <Avatar p={r} />
                    <span><span className="ot-name">{r.name}</span>
                      <div className="ot-count">{[r.role_label, r.department, data.scope === 'platform' ? r.organisation : null].filter(Boolean).join(' · ')}</div></span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        <button type="button" className="v-btn" onClick={() => setTick((n) => n + 1)}><RefreshCw size={13} /> Refresh</button>
      </div>

      {error && <div className="v-banner bad"><AlertCircle size={14} /><span>{error}</span></div>}
      {notice && <div className="v-banner ok"><span>{notice}</span></div>}

      <div className="oc-tools">
        <button type="button" className="ot-mini" onClick={() => setZoom((z) => Math.max(0.4, +(z - 0.1).toFixed(2)))} aria-label="Zoom out"><ZoomOut size={13} /></button>
        <span className="ot-count" style={{ minWidth: 38, textAlign: 'center' }}>{Math.round(zoom * 100)}%</span>
        <button type="button" className="ot-mini" onClick={() => setZoom((z) => Math.min(1.5, +(z + 0.1).toFixed(2)))} aria-label="Zoom in"><ZoomIn size={13} /></button>
        <button type="button" className="ot-mini" onClick={() => setZoom(1)}><Maximize2 size={12} /> 100%</button>
        <span className="grow" />
        <button type="button" className="ot-mini" onClick={expandAll}><ChevronsUpDown size={12} /> Expand all</button>
        <button type="button" className="ot-mini" onClick={() => setOpen(new Set(['root']))}><ChevronsDownUp size={12} /> Collapse all</button>
      </div>

      <div className="oc-viewport" ref={viewportRef}
        onWheel={() => { userMoved.current = true; }} onPointerDown={() => { userMoved.current = true; }}>
        {!data && !error && <div className="oc-team-empty" style={{ margin: '2rem auto' }}>Loading…</div>}
        {data && (
          <div className="oc" style={{ zoom }}>
            <ul>
              {data.scope === 'platform' ? (
                <li>
                  <Card kind="platform" icon={<Network size={15} />} title="Super Admin"
                    sub={`${orgs.length} organisations`} open={open.has('root')} onToggle={() => toggle('root')} hasChildren />
                  {open.has('root') && (
                    <ul>
                      {orgs.map((o) => (
                        <li key={o.id}>
                          <OrganisationNode org={o} isOpen={open.has(`o${o.id}`)} toggle={() => expandOrg(o.id)}
                            openSet={open} toggleSet={toggle} onOpen={(p) => setPerson(p.id)}
                            onAddDept={setAddingTo} onAssign={setAssigning} hitId={hitId} />
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ) : orgs.map((o) => (
                <li key={o.id || 'org'}>
                  <OrganisationNode org={o} isOpen={open.has(`o${o.id}`)} toggle={() => toggle(`o${o.id}`)}
                    openSet={open} toggleSet={toggle} onOpen={(p) => setPerson(p.id)}
                    onAddDept={setAddingTo} onAssign={setAssigning} hitId={hitId} />
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {addingTo && <AddDepartmentModal org={addingTo} onClose={() => setAddingTo(null)}
        onDone={(m) => { setAddingTo(null); changed(m); }} />}
      {assigning && <AssignAdminModal dept={assigning} onClose={() => setAssigning(null)}
        onDone={(m) => { setAssigning(null); changed(m); }} />}
      {person && <PersonPanel id={person} onClose={() => setPerson(null)} onChanged={changed} />}
    </DashboardLayout>
  );
}
