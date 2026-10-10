// src/pages/vault/DependencyMap.jsx
//
// The dependency map: which credentials feed which systems.
//
// Scoped by department, on the server. A Tenant Admin sees every system in
// the organisation and can filter by department here; everyone else sees
// their own department's systems plus the shared ones — the Production team
// sees production's dependencies, Testing sees testing's. Shared systems (the
// company VPN, email) are visible to everyone.
//
// Drawn as a bipartite SVG — credentials in the left column, systems in the
// right, links between. No graph library, because the data is bipartite by
// construction: an edge always runs credential → system, never between two of
// the same kind. A force-directed layout would spend its effort discovering
// structure we already know, and produce something harder to read.
//
// Hovering a node dims everything unconnected, which is how you actually
// answer "what does this touch" on a dense map.

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, Building2, CheckCircle, Network, Unlink } from 'lucide-react';

import DashboardLayout from '../../layouts/DashboardLayout';
import { useAuth } from '../../context/AuthContext';
import { vaultApi } from '../../services/api';
import { sidebarPropsFor } from '../../utils/sidebarRole';
import './vault.css';

const ROW = 34;
const TOP = 30;
const LEFT_X = 20;
const RIGHT_X = 420;
const NODE_W = 180;

const SHARED = 'shared';
const ALL = 'all';

// A stable colour per department, so the stripe on a system node means the
// same thing everywhere on the page. Shared systems get none.
const DEPT_COLOURS = ['#0ea5e9', '#a855f7', '#22c55e', '#f59e0b', '#ec4899', '#14b8a6', '#6366f1'];
const deptColour = (id) => (id == null ? null : DEPT_COLOURS[id % DEPT_COLOURS.length]);

export default function DependencyMap() {
  const { user } = useAuth();
  const [graph, setGraph] = useState(null);
  const [error, setError] = useState('');
  const [flash, setFlash] = useState('');
  const [hover, setHover] = useState(null); // {type, id}
  const [filter, setFilter] = useState(ALL);
  const [moving, setMoving] = useState(null); // system id being saved

  const reload = useCallback(
    () => vaultApi.dependencyGraph().then(setGraph, (e) => setError(e.message)),
    [],
  );

  useEffect(() => {
    let cancelled = false;
    vaultApi.dependencyGraph().then(
      (g) => { if (!cancelled) setGraph(g); },
      (e) => { if (!cancelled) setError(e.message); },
    );
    return () => { cancelled = true; };
  }, []);

  const allDepartments = !!graph?.scope?.all_departments;

  // Departments that appear on the map, for the filter. Built from the
  // systems themselves so a department with nothing in it does not clutter it.
  const deptOptions = useMemo(() => {
    if (!graph) return [];
    const seen = new Map();
    graph.systems.forEach((s) => {
      if (s.department_id != null) seen.set(s.department_id, s.department_name || `#${s.department_id}`);
    });
    return [...seen.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [graph]);

  // What is drawn, after the Tenant Admin's department filter.
  const view = useMemo(() => {
    if (!graph) return null;
    const keepSystem = (s) => (
      filter === ALL ? true
        : filter === SHARED ? s.department_id == null
          : String(s.department_id) === filter
    );
    const systems = graph.systems.filter(keepSystem);
    const systemIds = new Set(systems.map((s) => s.id));
    const edges = graph.edges.filter((e) => systemIds.has(e.system_id));
    const linked = new Set(edges.map((e) => e.credential_id));
    // Filtered: only credentials that touch what is shown. Unfiltered: every
    // credential the server sent, so unmapped ones stay visible.
    const credentials = filter === ALL
      ? graph.credentials
      : graph.credentials.filter((c) => linked.has(c.id));
    return { systems, edges, credentials };
  }, [graph, filter]);

  const positions = useMemo(() => {
    if (!view) return { creds: {}, systems: {} };
    const creds = {};
    const systems = {};
    view.credentials.forEach((c, i) => { creds[c.id] = TOP + i * ROW; });
    view.systems.forEach((s, i) => { systems[s.id] = TOP + i * ROW; });
    return { creds, systems };
  }, [view]);

  // Which nodes and edges stay bright while hovering.
  const active = useMemo(() => {
    if (!view || !hover) return null;
    const creds = new Set();
    const systems = new Set();
    const edges = new Set();

    view.edges.forEach((e, i) => {
      const match = hover.type === 'credential'
        ? e.credential_id === hover.id
        : e.system_id === hover.id;
      if (match) {
        creds.add(e.credential_id);
        systems.add(e.system_id);
        edges.add(i);
      }
    });
    if (hover.type === 'credential') creds.add(hover.id);
    else systems.add(hover.id);

    return { creds, systems, edges };
  }, [view, hover]);

  const dim = (on) => (active && !on ? 0.15 : 1);

  const height = view
    ? TOP + Math.max(view.credentials.length, view.systems.length) * ROW + 20
    : 200;

  // Credentials per system, for the table.
  const credCount = useMemo(() => {
    const n = {};
    (graph?.edges || []).forEach((e) => { n[e.system_id] = (n[e.system_id] || 0) + 1; });
    return n;
  }, [graph]);

  // Who may move which system. Mirrors the server: a Tenant Admin, any; an
  // Org Admin, only their own department's and shared ones. The server checks
  // again — this only decides whether to offer the control.
  const ownDept = graph?.scope?.department_id ?? null;
  const canMove = (s) => !!graph?.can_move_systems
    && (allDepartments || s.department_id == null || s.department_id === ownDept);

  const move = async (system, value) => {
    const departmentId = value === SHARED ? null : Number(value);
    setMoving(system.id);
    setError('');
    try {
      await vaultApi.moveSystem(system.id, departmentId);
      const where = departmentId == null
        ? 'shared with everyone'
        : `in ${(graph.departments || []).find((d) => d.id === departmentId)?.name || 'that department'}`;
      setFlash(`${system.name} is now ${where}.`);
      setTimeout(() => setFlash(''), 3500);
      await reload();
    } catch (err) {
      setError(err.message || 'Could not move that system.');
    } finally {
      setMoving(null);
    }
  };

  return (
    <DashboardLayout title="Dependency Map" {...sidebarPropsFor(user)}>
      <style>{`
        .dm-node { cursor:pointer; }
        .dm-label { font-size:11px; fill:var(--text2); font-family:var(--mono); }
        .dm-table { width:100%; border-collapse:collapse; font-size:.83rem; }
        .dm-table th { text-align:left; font-weight:500; color:var(--text3); font-size:.7rem;
          text-transform:uppercase; letter-spacing:.05em; padding:.5rem .6rem;
          border-bottom:1px solid var(--border); }
        .dm-table td { padding:.5rem .6rem; border-bottom:1px solid var(--border); color:var(--text2); }
        .dm-table tr:last-child td { border-bottom:none; }
        .dm-dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; vertical-align:0; }
      `}</style>

      {flash && (
        <div className="v-banner ok"><CheckCircle size={14} /><span>{flash}</span></div>
      )}
      {error && (
        <div className="v-banner bad">
          <AlertCircle size={14} />
          <span>{error}</span>
        </div>
      )}

      {graph && !allDepartments && (
        <div className="v-banner" style={{ background: 'rgba(14,165,233,.1)', color: 'var(--info)' }}>
          <Building2 size={14} />
          <span>
            {graph.scope.department_name
              ? <>Showing <strong>{graph.scope.department_name}</strong>&apos;s systems and the shared ones.</>
              : <>You are not in a department, so this shows the shared systems only.</>}
            {' '}Other departments&apos; systems are not shown.
          </span>
        </div>
      )}

      {graph && view && (
        <>
          <div className="v-stats">
            <div className="v-stat">
              <div className="v-stat-label">Credentials</div>
              <div className="v-stat-value">{view.credentials.length}</div>
            </div>
            <div className="v-stat">
              <div className="v-stat-label">Systems</div>
              <div className="v-stat-value">{view.systems.length}</div>
            </div>
            <div className="v-stat">
              <div className="v-stat-label">Links</div>
              <div className="v-stat-value">{view.edges.length}</div>
            </div>
            <div className="v-stat" style={{
              borderColor: graph.stats.unmapped_credentials
                ? 'rgba(245,158,11,.4)' : undefined }}>
              <div className="v-stat-label">Unmapped</div>
              <div className="v-stat-value"
                style={{ color: graph.stats.unmapped_credentials ? '#fbbf24' : 'inherit' }}>
                {graph.stats.unmapped_credentials}
              </div>
            </div>
          </div>

          {graph.stats.unmapped_credentials > 0 && (
            <div className="v-banner warn">
              <Unlink size={14} />
              <span>
                {graph.stats.unmapped_credentials} credential
                {graph.stats.unmapped_credentials === 1 ? ' has' : 's have'} no
                recorded dependencies. An unmapped credential is not a safe one —
                it is one whose blast radius is unknown.
              </span>
            </div>
          )}

          <div className="card-box" style={{ overflowX: 'auto' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '.8rem', flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: 220 }}>
                <h4 style={{ margin: '0 0 .3rem', fontSize: '.95rem' }}>
                  <Network size={14} style={{ verticalAlign: -2, marginRight: 6 }} />
                  Credentials → Systems
                </h4>
                <p style={{ fontSize: '.78rem', color: 'var(--text3)', marginTop: 0 }}>
                  Hover anything to isolate what it touches. The coloured edge on a
                  system is its department; no edge means shared.
                  {/* The graph is not scaled to fit narrow screens on purpose: at
                      phone width the labels would shrink to around six pixels and
                      the map would be decorative rather than readable. It scrolls
                      sideways instead, and says so. */}
                  <span className="v-scroll-hint"> Scroll sideways to see the full map.</span>
                </p>
              </div>
              {allDepartments && (deptOptions.length > 0 || graph.systems.some((s) => s.department_id == null)) && (
                <label className="v-field" style={{ minWidth: 190 }}>
                  <span>Department</span>
                  <select
                    className="form-select"
                    value={filter}
                    onChange={(e) => { setFilter(e.target.value); setHover(null); }}
                  >
                    <option value={ALL}>All departments</option>
                    {deptOptions.map(([id, name]) => (
                      <option key={id} value={String(id)}>{name}</option>
                    ))}
                    <option value={SHARED}>Shared only</option>
                  </select>
                </label>
              )}
            </div>

            <svg width={RIGHT_X + NODE_W + 40} height={height}
              style={{ minWidth: 640 }}>
              {/* edges under nodes so they never cover a label */}
              {view.edges.map((e, i) => {
                const y1 = positions.creds[e.credential_id];
                const y2 = positions.systems[e.system_id];
                if (y1 === undefined || y2 === undefined) return null;
                const x1 = LEFT_X + NODE_W;
                const x2 = RIGHT_X;
                const mid = (x1 + x2) / 2;
                return (
                  <path
                    key={i}
                    d={`M ${x1} ${y1 + 11} C ${mid} ${y1 + 11}, ${mid} ${y2 + 11}, ${x2} ${y2 + 11}`}
                    fill="none"
                    stroke={active?.edges.has(i) ? '#0ea5e9' : 'var(--border)'}
                    strokeWidth={active?.edges.has(i) ? 2 : 1}
                    opacity={dim(active?.edges.has(i))}
                  />
                );
              })}

              {view.credentials.map((c) => (
                <g key={`c${c.id}`} className="dm-node"
                  opacity={dim(active?.creds.has(c.id))}
                  onMouseEnter={() => setHover({ type: 'credential', id: c.id })}
                  onMouseLeave={() => setHover(null)}>
                  <title>{c.name}{c.unmapped ? ' — no recorded dependencies' : ''}</title>
                  <rect x={LEFT_X} y={positions.creds[c.id]} width={NODE_W} height={22}
                    rx={6} fill="var(--bg3)"
                    stroke={c.unmapped ? '#f59e0b' : 'var(--border)'} />
                  <text className="dm-label" x={LEFT_X + 8}
                    y={positions.creds[c.id] + 15}>
                    {c.name.length > 22 ? `${c.name.slice(0, 21)}…` : c.name}
                  </text>
                </g>
              ))}

              {view.systems.map((s) => {
                const prod = (s.environment || '').toLowerCase().startsWith('prod');
                const stripe = deptColour(s.department_id);
                return (
                  <g key={`s${s.id}`} className="dm-node"
                    opacity={dim(active?.systems.has(s.id))}
                    onMouseEnter={() => setHover({ type: 'system', id: s.id })}
                    onMouseLeave={() => setHover(null)}>
                    <title>
                      {s.name}
                      {s.environment ? ` (${s.environment})` : ''}
                      {` — ${s.department_name || 'shared with everyone'}`}
                    </title>
                    <rect x={RIGHT_X} y={positions.systems[s.id]} width={NODE_W}
                      height={22} rx={6}
                      fill={prod ? 'rgba(239,68,68,.12)' : 'var(--bg3)'}
                      stroke={prod ? 'rgba(239,68,68,.5)' : 'var(--border)'} />
                    {stripe && (
                      <rect x={RIGHT_X} y={positions.systems[s.id]} width={4} height={22}
                        rx={2} fill={stripe} />
                    )}
                    <text className="dm-label" x={RIGHT_X + 10}
                      y={positions.systems[s.id] + 15}>
                      {s.name.length > 20 ? `${s.name.slice(0, 19)}…` : s.name}
                      {s.environment ? ` (${s.environment.slice(0, 4)})` : ''}
                    </text>
                  </g>
                );
              })}
            </svg>

            {view.credentials.length === 0 && view.systems.length === 0 && (
              <div className="v-empty">
                <div className="v-empty-icon"><Network size={22} strokeWidth={1.5} /></div>
                <div className="v-empty-title">Nothing mapped yet</div>
                <p className="v-empty-body">
                  Once credentials are linked to the systems that use them, this
                  map shows what a rotation would break before you rotate it.
                </p>
              </div>
            )}
          </div>

          {view.systems.length > 0 && (
            <div className="card-box" style={{ marginTop: '1rem', overflowX: 'auto' }}>
              <h4 style={{ margin: '0 0 .6rem', fontSize: '.95rem' }}>
                <Building2 size={14} style={{ verticalAlign: -2, marginRight: 6 }} />
                Systems by department
              </h4>
              <table className="dm-table">
                <thead>
                  <tr>
                    <th>System</th>
                    <th>Environment</th>
                    <th>Credentials</th>
                    <th>Department</th>
                  </tr>
                </thead>
                <tbody>
                  {view.systems.map((s) => (
                    <tr key={s.id}>
                      <td style={{ color: 'var(--text)', fontWeight: 500 }}>{s.name}</td>
                      <td>{s.environment || '—'}</td>
                      <td>{credCount[s.id] || 0}</td>
                      <td>
                        {canMove(s) ? (
                          <select
                            className="form-select"
                            value={s.department_id == null ? SHARED : String(s.department_id)}
                            disabled={moving === s.id}
                            onChange={(e) => move(s, e.target.value)}
                            aria-label={`Department for ${s.name}`}
                            style={{ minWidth: 160 }}
                          >
                            <option value={SHARED}>Shared with everyone</option>
                            {(graph.departments || []).map((d) => (
                              <option key={d.id} value={String(d.id)}>{d.name}</option>
                            ))}
                          </select>
                        ) : (
                          <span>
                            {deptColour(s.department_id) && (
                              <span className="dm-dot" style={{ background: deptColour(s.department_id) }} />
                            )}
                            {s.department_name || 'Shared with everyone'}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </DashboardLayout>
  );
}
