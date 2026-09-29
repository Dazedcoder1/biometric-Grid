// src/pages/vault/CredentialDetail.jsx
//
// One credential: its sharing tree and its activity timeline.
//
// The tree is rendered as an indented list with connector lines rather than
// with React Flow or D3. A share tree is almost always two or three levels
// deep and read top-to-bottom, so a graph canvas would add a dependency, a
// bundle, and pan/zoom controls nobody needs — and would be harder to read.
// The server already returns the tree flat with a depth on each node, which is
// exactly the shape this needs.

import React, { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  AlertCircle, ArrowLeft, Clock, Share2, ShieldOff, UserPlus, X,
} from 'lucide-react';

import DashboardLayout from '../../layouts/DashboardLayout';
import ConfirmationModal from '../../components/ConfirmationModal';
import { useAuth } from '../../context/AuthContext';
import { vaultApi } from '../../services/api';
import { sidebarPropsFor } from '../../utils/sidebarRole';

const LEVELS = ['view', 'reveal', 'edit', 'reshare', 'manage'];

const STATUS_TONE = {
  active: '#22c55e',
  pending: '#f59e0b',
  expired: '#6b7280',
  revoked: '#ef4444',
};

export default function CredentialDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const [tree, setTree] = useState([]);
  const [timeline, setTimeline] = useState([]);
  const [error, setError] = useState('');
  const [flash, setFlash] = useState('');
  const [showShare, setShowShare] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState(null);

  const note = (m) => { setFlash(m); setTimeout(() => setFlash(''), 4000); };

  const load = useCallback(async () => {
    try {
      const [t, a] = await Promise.all([
        vaultApi.shareTree(id),
        vaultApi.activity(id),
      ]);
      setTree(t);
      setTimeline(a);
    } catch (err) {
      setError(err.message);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const handleRevoke = async () => {
    try {
      const res = await vaultApi.revokeShare(revokeTarget.id);
      setRevokeTarget(null);
      // Say plainly how many others lost access. Cascading silently is how
      // people get cut off without anyone realising.
      note(
        res.cascaded > 0
          ? `Revoked. ${res.cascaded} further share${res.cascaded === 1 ? '' : 's'} granted through it were also revoked.`
          : 'Share revoked.',
      );
      await load();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <DashboardLayout title="Credential" {...sidebarPropsFor(user)}>
      <style>{`
        .cd-node { display:flex; align-items:center; gap:.75rem;
          padding:.6rem .8rem; border-radius:8px; }
        .cd-node:hover { background:var(--bg3); }
        .cd-dot { width:8px; height:8px; border-radius:50%; flex:none; }
        .cd-rail { border-left:1px dashed var(--border); margin-left:.45rem;
          padding-left:1rem; }
        .cd-btn { background:var(--bg3); border:1px solid var(--border);
          border-radius:8px; padding:.35rem .6rem; cursor:pointer;
          color:var(--text2); font-size:.78rem; display:inline-flex;
          align-items:center; gap:.35rem; }
        .cd-btn:hover { background:var(--bg4); color:var(--text); }
        .cd-overlay { position:fixed; inset:0; background:rgba(0,0,0,.8);
          backdrop-filter:blur(6px); display:flex; align-items:center;
          justify-content:center; z-index:9999; }
        .cd-modal { background:var(--bg2); border:1px solid var(--border);
          border-radius:18px; width:min(440px,92vw); padding:1.5rem;
          position:relative; }
        .cd-event { display:flex; gap:.75rem; padding:.55rem 0;
          border-top:1px solid var(--border); font-size:.84rem; }
      `}</style>

      <a href="/vault" className="cd-btn" style={{ marginBottom: '1rem' }}>
        <ArrowLeft size={13} /> Back to vault
      </a>

      {flash && (
        <div style={{ padding: '.6rem .8rem', borderRadius: 8, marginBottom: '1rem',
          background: 'rgba(34,197,94,.12)', fontSize: '.85rem' }}>{flash}</div>
      )}
      {error && (
        <div style={{ padding: '.6rem .8rem', borderRadius: 8, marginBottom: '1rem',
          background: 'rgba(239,68,68,.12)', fontSize: '.85rem' }}>
          <AlertCircle size={13} style={{ verticalAlign: -2, marginRight: 6 }} />
          {error}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem' }}>
        {/* ─── sharing tree ─────────────────────────────────────────── */}
        <div className="card-box">
          <div style={{ display: 'flex', justifyContent: 'space-between',
            alignItems: 'center', marginBottom: '.6rem' }}>
            <h4 style={{ margin: 0, fontSize: '.95rem' }}>
              <Share2 size={14} style={{ verticalAlign: -2, marginRight: 6 }} />
              Who has access
            </h4>
            <button className="cd-btn" onClick={() => setShowShare(true)}>
              <UserPlus size={13} /> Share
            </button>
          </div>

          {tree.length === 0 ? (
            <div style={{ opacity: .6, fontSize: '.85rem', padding: '1rem 0' }}>
              Not shared with anyone. Only you can see this.
            </div>
          ) : (
            tree.map((node) => (
              <div key={node.id} style={{ marginLeft: node.depth * 18 }}>
                <div className={node.depth > 0 ? 'cd-rail' : ''}>
                  <div className="cd-node">
                    <span className="cd-dot"
                      style={{ background: STATUS_TONE[node.status] }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: '.85rem' }}>
                        {node.grantee_user_id
                          ? `User #${node.grantee_user_id}`
                          : `Team #${node.grantee_team_id}`}
                        <span style={{ opacity: .6, marginLeft: 6 }}>
                          · {node.permission}
                        </span>
                      </div>
                      <div style={{ fontSize: '.72rem', opacity: .6 }}>
                        {node.depth > 0 && `via user #${node.grantor_id} · `}
                        {node.status}
                        {node.expires_at &&
                          ` · expires ${new Date(node.expires_at).toLocaleString()}`}
                        {node.revoked_reason && ` · ${node.revoked_reason}`}
                      </div>
                    </div>
                    {['active', 'pending'].includes(node.status) && (
                      <button className="cd-btn" onClick={() => setRevokeTarget(node)}>
                        <ShieldOff size={12} />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        {/* ─── timeline ─────────────────────────────────────────────── */}
        <div className="card-box">
          <h4 style={{ margin: '0 0 .6rem', fontSize: '.95rem' }}>
            <Clock size={14} style={{ verticalAlign: -2, marginRight: 6 }} />
            Activity
          </h4>

          {timeline.length === 0 ? (
            <div style={{ opacity: .6, fontSize: '.85rem' }}>Nothing recorded yet.</div>
          ) : (
            timeline.map((e) => (
              <div key={e.seq} className="cd-event">
                <div style={{ flex: 1 }}>
                  <div>
                    <strong>
                      {e.actor_id ? `User #${e.actor_id}` : 'System'}
                    </strong>{' '}
                    <span style={{
                      color: e.result === 'denied' ? '#ef4444'
                        : e.action === 'credential.tamper_detected' ? '#ef4444'
                          : 'inherit',
                    }}>
                      {e.label}
                    </span>
                    {e.result === 'denied' && (
                      <span style={{ color: '#ef4444', fontSize: '.72rem' }}>
                        {' '}— denied
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: '.72rem', opacity: .55 }}>
                    {new Date(e.occurred_at).toLocaleString()}
                    {e.source_ip && ` · ${e.source_ip}`}
                    {e.mfa_method && ` · ${e.mfa_method}`}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {showShare && (
        <ShareModal
          credentialId={id}
          onClose={() => setShowShare(false)}
          onShared={async () => { setShowShare(false); note('Shared.'); await load(); }}
          onError={setError}
        />
      )}

      <ConfirmationModal
        isOpen={!!revokeTarget}
        title="Revoke access"
        message={
          'This removes their access, and everything they shared onward. '
          + 'Revoked shares stay in the record — nothing is deleted.'
        }
        confirmText="Revoke"
        type="danger"
        onConfirm={handleRevoke}
        onClose={() => setRevokeTarget(null)}
      />
    </DashboardLayout>
  );
}

function ShareModal({ credentialId, onClose, onShared, onError }) {
  const [form, setForm] = useState({
    grantee_user_id: '', permission: 'view', expires_at: '',
  });
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await vaultApi.share(credentialId, {
        grantee_user_id: Number(form.grantee_user_id),
        permission: form.permission,
        // datetime-local gives a naive string; the server treats a missing
        // offset as UTC, so send it explicitly rather than relying on that.
        expires_at: form.expires_at
          ? new Date(form.expires_at).toISOString()
          : null,
      });
      await onShared();
    } catch (err) {
      onError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="cd-overlay">
      <form className="cd-modal" onSubmit={submit}>
        <button type="button" onClick={onClose} style={{ position: 'absolute',
          top: 14, right: 14, background: 'none', border: 'none',
          color: 'var(--text3)', cursor: 'pointer' }}>
          <X size={18} />
        </button>
        <h3 style={{ marginTop: 0, fontSize: '1.05rem' }}>Share credential</h3>

        <label className="form-label">User ID</label>
        <input className="form-input" required type="number"
          value={form.grantee_user_id}
          onChange={(e) => setForm({ ...form, grantee_user_id: e.target.value })}
          style={{ width: '100%', marginBottom: '.7rem' }} />

        <label className="form-label">Permission</label>
        <select className="form-input" value={form.permission}
          onChange={(e) => setForm({ ...form, permission: e.target.value })}
          style={{ width: '100%', marginBottom: '.4rem' }}>
          {LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
        </select>
        <div style={{ fontSize: '.72rem', opacity: .65, marginBottom: '.7rem' }}>
          You cannot grant more than you hold. `reveal` lets them see the secret;
          `view` shows only that it exists.
        </div>

        <label className="form-label">Expires (optional)</label>
        <input className="form-input" type="datetime-local" value={form.expires_at}
          onChange={(e) => setForm({ ...form, expires_at: e.target.value })}
          style={{ width: '100%' }} />
        <div style={{ fontSize: '.72rem', opacity: .65, marginTop: '.3rem' }}>
          Leave blank for access that does not expire.
        </div>

        <button type="submit" disabled={busy || !form.grantee_user_id}
          style={{ width: '100%', marginTop: '1rem', padding: '.7rem',
            borderRadius: 10, border: 'none', background: 'var(--teal)',
            color: '#fff', fontWeight: 600, cursor: 'pointer' }}>
          {busy ? 'Sharing…' : 'Share'}
        </button>
      </form>
    </div>
  );
}
