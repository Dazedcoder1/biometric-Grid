// src/components/HrToggle.jsx
//
// "Make HR" / "Remove HR" on a person's card. HR access adds payroll and
// expense claims for the whole organisation on top of their own role; they
// keep everything they had. Needs role.assign — a Tenant Admin signed in with
// a password, or a Super Admin. An API-key session has no person to record
// as having granted it, so the button is not offered there.

import React, { useState } from 'react';
import { Briefcase } from 'lucide-react';

import { useAuth } from '../context/AuthContext';
import { accountsApi } from '../services/api';

export function HrBadge() {
  return (
    <span
      title="Has HR access: payroll and expense claims"
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 3, marginLeft: 6, padding: '1px 7px',
        borderRadius: 999, fontSize: '.65rem', fontWeight: 700, letterSpacing: '.03em',
        background: 'rgba(168,85,247,.14)', color: 'var(--purple)', verticalAlign: 'middle',
      }}
    >
      <Briefcase size={10} /> HR
    </span>
  );
}

export default function HrToggle({ person, onChange }) {
  const { user } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  if (!user || user.viaApiKey) return null;

  const isHr = !!person.is_hr;

  const toggle = async () => {
    const question = isHr
      ? `Remove HR access from ${person.name}? They will no longer see payroll.`
      : `Give ${person.name} HR access? They will be able to run payroll, see salaries and approve expense claims for the whole organisation.`;
    if (!window.confirm(question)) return;
    setBusy(true);
    setError('');
    try {
      const res = await accountsApi.setHr(person.id, !isHr);
      onChange?.(res.is_hr);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <span style={{ display: 'inline-flex', flexDirection: 'column', gap: 4 }}>
      <button
        type="button"
        className="btn btn-ghost"
        onClick={toggle}
        disabled={busy}
        style={{ fontSize: '0.75rem', padding: '4px 10px', display: 'inline-flex', alignItems: 'center', gap: 5 }}
      >
        <Briefcase size={13} />
        {busy ? 'Saving…' : isHr ? 'Remove HR' : 'Make HR'}
      </button>
      {error && <span role="alert" style={{ color: 'var(--bad)', fontSize: '.7rem' }}>{error}</span>}
    </span>
  );
}
