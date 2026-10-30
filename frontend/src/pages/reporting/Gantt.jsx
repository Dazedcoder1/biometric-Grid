// src/pages/reporting/Gantt.jsx
//
// A simple Gantt timeline: one row per target, months across the top, each
// target a bar from its start to its end, filled to its progress and
// coloured by health (on track, at risk, overdue, done). Milestones are
// diamonds on the bar. Pure CSS/DOM — no charting library.

import React, { useMemo } from 'react';

const DAY = 86400000;

function parse(d) { return new Date(`${d}T00:00:00`); }
function monthKey(d) { return `${d.getFullYear()}-${d.getMonth()}`; }

export function STATE_COLOUR() {
  return {
    on_track: 'On track', at_risk: 'At risk', overdue: 'Overdue',
    done: 'Done', upcoming: 'Upcoming', cancelled: 'Cancelled',
  };
}

export default function Gantt({ targets, onOpen }) {
  const model = useMemo(() => {
    if (!targets.length) return null;
    let min = parse(targets[0].start_date);
    let max = parse(targets[0].end_date);
    targets.forEach((t) => {
      const s = parse(t.start_date);
      const e = parse(t.end_date);
      if (s < min) min = s;
      if (e > max) max = e;
    });
    // Snap to month boundaries, and pad a little.
    const start = new Date(min.getFullYear(), min.getMonth(), 1);
    const end = new Date(max.getFullYear(), max.getMonth() + 1, 0);
    const months = [];
    const cur = new Date(start);
    while (cur <= end) {
      months.push(new Date(cur));
      cur.setMonth(cur.getMonth() + 1);
    }
    const totalDays = Math.max(1, (end - start) / DAY);
    const pctOf = (d) => `${Math.max(0, Math.min(100, ((parse(d) - start) / DAY / totalDays) * 100))}%`;
    const today = new Date();
    const todayPct = today >= start && today <= end ? ((today - start) / DAY / totalDays) * 100 : null;
    return { start, end, months, totalDays, pctOf, todayPct };
  }, [targets]);

  if (!model) return null;
  const { start, months, totalDays, pctOf, todayPct } = model;
  const labelCol = 220;
  const gridCols = `${labelCol}px repeat(${months.length}, 1fr)`;
  const spanLeft = (s) => ((parse(s) - start) / DAY / totalDays) * 100;
  const spanWidth = (s, e) => Math.max(1.2, ((parse(e) - parse(s) + DAY) / DAY / totalDays) * 100);

  return (
    <div className="gantt">
      <div className="gantt-scroll">
        <div className="gantt-grid gantt-head" style={{ gridTemplateColumns: gridCols }}>
          <div className="gantt-month" style={{ borderLeft: 'none', textAlign: 'left' }}>Target</div>
          {months.map((m) => (
            <div key={monthKey(m)} className="gantt-month">
              {m.toLocaleDateString('en-IN', { month: 'short' })}{m.getMonth() === 0 ? ` '${String(m.getFullYear()).slice(2)}` : ''}
            </div>
          ))}
        </div>
        {targets.map((t) => (
          <div key={t.id} className="gantt-grid" style={{ gridTemplateColumns: gridCols }}>
            <div className="gantt-rowlabel" onClick={() => onOpen?.(t)}>
              <span className="t">{t.title}</span>
              <span className="o">{t.scope === 'department' ? `Dept: ${t.department || '—'}` : (t.owner || '—')} · {t.progress}%</span>
            </div>
            <div className="gantt-track" style={{ gridColumn: `2 / span ${months.length}` }}>
              {months.slice(1).map((m, i) => (
                <div key={i} className="monthline" style={{ left: `${((new Date(m.getFullYear(), m.getMonth(), 1) - start) / DAY / totalDays) * 100}%` }} />
              ))}
              {todayPct != null && <div className="gantt-today" style={{ left: `${todayPct}%` }} title="Today" />}
              <button type="button" className={`gantt-bar ${t.state}`} onClick={() => onOpen?.(t)}
                title={`${t.title} — ${t.progress}% (${t.state.replace('_', ' ')})`}
                style={{ left: `${spanLeft(t.start_date)}%`, width: `${spanWidth(t.start_date, t.end_date)}%`, '--pct': `${t.progress}%` }}>
                <span className="fill" />
                <span className="lbl">{t.progress}%</span>
              </button>
              {t.milestones.filter((m) => m.due_date).map((m) => (
                <span key={m.id} className={`gantt-ms ${m.done ? 'done' : ''}`}
                  style={{ left: pctOf(m.due_date) }} title={`${m.title}${m.done ? ' ✓' : ''} — ${m.due_date}`} />
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="gantt-legend">
        <span><i style={{ background: 'var(--teal)' }} /> On track</span>
        <span><i style={{ background: 'var(--amber)' }} /> At risk</span>
        <span><i style={{ background: 'var(--red)' }} /> Overdue</span>
        <span><i style={{ background: 'var(--green)' }} /> Done</span>
        <span><i style={{ background: 'var(--text3)' }} /> Upcoming</span>
        <span style={{ marginLeft: 'auto' }}><i style={{ background: 'var(--red)', width: 2, height: 11 }} /> Today · ◆ milestone</span>
      </div>
    </div>
  );
}
