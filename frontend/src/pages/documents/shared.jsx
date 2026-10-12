// src/pages/documents/shared.jsx — pieces the HR document screens share.

import React, { useEffect, useState } from 'react';
import { History } from 'lucide-react';

import VaultModal from '../../components/VaultModal';
import { documentsApi } from '../../services/api';
import '../vault/vault.css';
import '../../components/clock.css';
import '../payroll/payroll.css';
import './documents.css';
import { ACTION_TEXT, fmtDateTime } from '../../utils/docFormat';

/** draft / issued / revoked, and expiry: valid / expiring / expired / none. */
export function Pill({ value, label }) {
  return <span className={`pr-status ${value}`}>{label || value}</span>;
}

export function ExpiryPill({ state, daysLeft }) {
  if (state === 'none') return <span className="ct-sub">No expiry</span>;
  if (state === 'expired') return <span className="pr-status rejected">Expired {Math.abs(daysLeft)}d ago</span>;
  if (state === 'expiring') return <span className="pr-status pending">{daysLeft === 0 ? 'Expires today' : `${daysLeft}d left`}</span>;
  return <span className="pr-status paid">Valid</span>;
}

/** Who did what to one letter or document — every view and download. */
export function AccessLogButton({ targetType, targetId, title }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className="v-btn" onClick={() => setOpen(true)}>
        <History size={13} /> Access log
      </button>
      {open && <AccessLog targetType={targetType} targetId={targetId} title={title} onClose={() => setOpen(false)} />}
    </>
  );
}

function AccessLog({ targetType, targetId, title, onClose }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    documentsApi.accessLog(targetType, targetId).then(
      (r) => { if (!cancelled) setRows(r); },
      (err) => { if (!cancelled) setError(err.message); },
    );
    return () => { cancelled = true; };
  }, [targetType, targetId]);
  return (
    <VaultModal title={`Access log — ${title}`} onClose={onClose} width={640}>
      {error && <div className="v-banner bad"><span>{error}</span></div>}
      {!rows && !error && <p className="pr-sub">Loading…</p>}
      {rows && rows.length === 0 && <p className="pr-sub">Nothing recorded yet.</p>}
      {rows && rows.length > 0 && (
        <div className="doc-log">
          {rows.map((r) => (
            <div key={r.seq} className="doc-log-row">
              <span className="doc-log-when">{fmtDateTime(r.occurred_at)}</span>
              <span><b>{r.actor || 'System'}</b> · {ACTION_TEXT[r.action] || r.action}
                {r.details?.version ? ` (v${r.details.version})` : ''}</span>
              <span className="ct-sub">{r.source_ip || ''}</span>
            </div>
          ))}
        </div>
      )}
      <p className="pr-sub" style={{ marginTop: '.8rem' }}>Also in the organisation's Audit Log, which is tamper-evident.</p>
    </VaultModal>
  );
}

/** A people picker fed by /api/documents/people. */
export function PersonSelect({ people, value, onChange, required }) {
  return (
    <select value={value} required={required} onChange={(e) => onChange(e.target.value)}>
      <option value="">Choose a person…</option>
      {people.filter((p) => p.is_active).map((p) => (
        <option key={p.id} value={p.id}>
          {p.name}{p.employee_code ? ` (${p.employee_code})` : ''}{p.department ? ` — ${p.department}` : ''}
        </option>
      ))}
    </select>
  );
}
