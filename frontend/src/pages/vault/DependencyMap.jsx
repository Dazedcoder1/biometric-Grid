// src/pages/vault/DependencyMap.jsx
//
// The org-wide dependency map: which credentials feed which systems.
//
// Drawn as a bipartite SVG — credentials in the left column, systems in the
// right, links between. No graph library, because the data is bipartite by
// construction: an edge always runs credential → system, never between two of
// the same kind. A force-directed layout would spend its effort discovering
// structure we already know, and produce something harder to read.
//
// Hovering a node dims everything unconnected, which is how you actually
// answer "what does this touch" on a dense map.

import React, { useEffect, useMemo, useState } from 'react';
import { AlertCircle, Network, Unlink } from 'lucide-react';

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

export default function DependencyMap() {
  const { user } = useAuth();
  const [graph, setGraph] = useState(null);
  const [error, setError] = useState('');
  const [hover, setHover] = useState(null); // {type, id}

  useEffect(() => {
    vaultApi.dependencyGraph().then(setGraph).catch((e) => setError(e.message));
  }, []);

  const positions = useMemo(() => {
    if (!graph) return { creds: {}, systems: {} };
    const creds = {};
    const systems = {};
    graph.credentials.forEach((c, i) => { creds[c.id] = TOP + i * ROW; });
    graph.systems.forEach((s, i) => { systems[s.id] = TOP + i * ROW; });
    return { creds, systems };
  }, [graph]);

  // Which nodes and edges stay bright while hovering.
  const active = useMemo(() => {
    if (!graph || !hover) return null;
    const creds = new Set();
    const systems = new Set();
    const edges = new Set();

    graph.edges.forEach((e, i) => {
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
  }, [graph, hover]);

  const dim = (on) => (active && !on ? 0.15 : 1);

  const height = graph
    ? TOP + Math.max(graph.credentials.length, graph.systems.length) * ROW + 20
    : 200;

  return (
    <DashboardLayout title="Dependency Map" {...sidebarPropsFor(user)}>
      <style>{`
        .dm-node { cursor:pointer; }
        .dm-label { font-size:11px; fill:var(--text2); font-family:var(--mono); }
      `}</style>

      {error && (
        <div className="v-banner bad">
          <AlertCircle size={14} />
          <span>{error}</span>
        </div>
      )}

      {graph && (
        <>
          <div className="v-stats">
            <div className="v-stat">
              <div className="v-stat-label">Credentials</div>
              <div className="v-stat-value">{graph.stats.credentials}</div>
            </div>
            <div className="v-stat">
              <div className="v-stat-label">Systems</div>
              <div className="v-stat-value">{graph.stats.systems}</div>
            </div>
            <div className="v-stat">
              <div className="v-stat-label">Links</div>
              <div className="v-stat-value">{graph.stats.links}</div>
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
            <h4 style={{ margin: '0 0 .3rem', fontSize: '.95rem' }}>
              <Network size={14} style={{ verticalAlign: -2, marginRight: 6 }} />
              Credentials → Systems
            </h4>
            <p style={{ fontSize: '.78rem', color: 'var(--text3)', marginTop: 0 }}>
              Hover anything to isolate what it touches.
              {/* The graph is not scaled to fit narrow screens on purpose: at
                  phone width the labels would shrink to around six pixels and
                  the map would be decorative rather than readable. It scrolls
                  sideways instead, and says so. */}
              <span className="v-scroll-hint"> Scroll sideways to see the full map.</span>
            </p>

            <svg width={RIGHT_X + NODE_W + 40} height={height}
              style={{ minWidth: 640 }}>
              {/* edges under nodes so they never cover a label */}
              {graph.edges.map((e, i) => {
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

              {graph.credentials.map((c) => (
                <g key={`c${c.id}`} className="dm-node"
                  opacity={dim(active?.creds.has(c.id))}
                  onMouseEnter={() => setHover({ type: 'credential', id: c.id })}
                  onMouseLeave={() => setHover(null)}>
                  <rect x={LEFT_X} y={positions.creds[c.id]} width={NODE_W} height={22}
                    rx={6} fill="var(--bg3)"
                    stroke={c.unmapped ? '#f59e0b' : 'var(--border)'} />
                  <text className="dm-label" x={LEFT_X + 8}
                    y={positions.creds[c.id] + 15}>
                    {c.name.length > 22 ? `${c.name.slice(0, 21)}…` : c.name}
                  </text>
                </g>
              ))}

              {graph.systems.map((s) => {
                const prod = (s.environment || '').toLowerCase().startsWith('prod');
                return (
                  <g key={`s${s.id}`} className="dm-node"
                    opacity={dim(active?.systems.has(s.id))}
                    onMouseEnter={() => setHover({ type: 'system', id: s.id })}
                    onMouseLeave={() => setHover(null)}>
                    <rect x={RIGHT_X} y={positions.systems[s.id]} width={NODE_W}
                      height={22} rx={6}
                      fill={prod ? 'rgba(239,68,68,.12)' : 'var(--bg3)'}
                      stroke={prod ? 'rgba(239,68,68,.5)' : 'var(--border)'} />
                    <text className="dm-label" x={RIGHT_X + 8}
                      y={positions.systems[s.id] + 15}>
                      {s.name.length > 20 ? `${s.name.slice(0, 19)}…` : s.name}
                      {s.environment ? ` (${s.environment.slice(0, 4)})` : ''}
                    </text>
                  </g>
                );
              })}
            </svg>

            {graph.credentials.length === 0 && (
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
        </>
      )}
    </DashboardLayout>
  );
}
