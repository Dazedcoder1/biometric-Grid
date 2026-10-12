// src/components/PendingDocsBanner.jsx
//
// "2 policies are waiting for your acknowledgement" on the dashboard, so a new
// policy version is not only a notification that scrolls away.

import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { FileWarning } from 'lucide-react';

import { documentsApi } from '../services/api';
import '../pages/documents/documents.css';

export default function PendingDocsBanner() {
  const [pending, setPending] = useState(null);
  useEffect(() => {
    let cancelled = false;
    documentsApi.myPending().then((p) => { if (!cancelled) setPending(p); }, () => {});
    return () => { cancelled = true; };
  }, []);
  if (!pending) return null;
  const n = pending.policies.length;
  const l = pending.letters;
  if (!n && !l) return null;
  const parts = [];
  if (n) parts.push(n === 1 ? `“${pending.policies[0].title}” is waiting for your acknowledgement` : `${n} policies are waiting for your acknowledgement`);
  if (l) parts.push(`${l} new letter${l === 1 ? '' : 's'}`);
  return (
    <div className="doc-banner" role="status">
      <FileWarning size={16} />
      <span>{parts.join(' · ')}.</span>
      <Link to="/my-documents">Open My Documents</Link>
    </div>
  );
}
