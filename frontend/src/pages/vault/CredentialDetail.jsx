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
import { Link, useParams } from 'react-router-dom';
import {
  AlertCircle, ArrowLeft, CheckCircle, Clock, Share2, ShieldOff, UserPlus, Users,
} from 'lucide-react';

import DashboardLayout from '../../layouts/DashboardLayout';
import ConfirmationModal from '../../components/ConfirmationModal';
import { useAuth } from '../../context/AuthContext';
import usePermissions from '../../hooks/usePermissions';
import { vaultApi } from '../../services/api';
import { sidebarPropsFor } from '../../utils/sidebarRole';
import VaultModal from '../../components/VaultModal';
import './vault.css';

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
  const { can } = usePermissions();
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
      {/* Link, not <a href>: an anchor reloads the whole app and re-runs auth
          just to go back one screen. */}
      <Link to="/vault" className="v-btn"
        style={{ marginBottom: '1rem', display: 'inline-flex' }}>
        <ArrowLeft size={13} /> Back to vault
      </Link>

      {flash && (
        <div className="v-banner ok"><CheckCircle size={14} /><span>{flash}</span></div>
      )}
      {error && (
        <div className="v-banner bad"><AlertCircle size={14} /><span>{error}</span></div>
      )}

      <div className="v-split">
        {/* ─── sharing tree ─────────────────────────────────────────── */}
        <div className="card-box">
          <div style={{ display: 'flex', justifyContent: 'space-between',
            alignItems: 'center', marginBottom: '.6rem' }}>
            <h4 style={{ margin: 0, fontSize: '.95rem' }}>
              <Share2 size={14} style={{ verticalAlign: -2, marginRight: 6 }} />
              Who has access
            </h4>
            {/* share.view opens this page; share.grant is what the button
                actually needs. They are separate permissions and an Employee
                holds only the first. */}
            {can('share.grant') && (
              <button type="button" className="v-btn" onClick={() => setShowShare(true)}>
                <UserPlus size={13} /> Share
              </button>
            )}
          </div>

          {tree.length === 0 ? (
            <div className="v-empty" style={{ padding: '2rem 1rem' }}>
              <div className="v-empty-icon"><Users size={22} strokeWidth={1.5} /></div>
              <div className="v-empty-title">Not shared with anyone</div>
              <p className="v-empty-body">
                Only you can see this credential. Sharing grants a specific level
                — view, reveal, edit, reshare or manage — and can be time-limited.
              </p>
            </div>
          ) : (
            tree.map((node) => (
              // Indent is capped at four levels. Past that a reshared credential
              // walks its own tree off the right edge on a narrow screen, and
              // the connector rails already show the nesting.
              <div key={node.id} style={{ marginLeft: Math.min(node.depth, 4) * 18 }}>
                <div className={node.depth > 0 ? 'v-rail' : ''}>
                  <div className="v-node">
                    <span className="v-dot"
                      style={{ background: STATUS_TONE[node.status] }}
                      title={node.status} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: '.85rem' }}>
                        {node.grantee_user_id
                          ? `User #${node.grantee_user_id}`
                          : `Team #${node.grantee_team_id}`}
                        <span className="v-chip" style={{ marginLeft: 6 }}>
                          {node.permission}
                        </span>
                      </div>
                      <div style={{ fontSize: '.72rem', color: 'var(--text3)' }}>
                        {node.depth > 0 && `via user #${node.grantor_id} · `}
                        {node.status}
                        {node.expires_at &&
                          ` · expires ${new Date(node.expires_at).toLocaleString()}`}
                        {node.revoked_reason && ` · ${node.revoked_reason}`}
                      </div>
                    </div>
                    {can('share.revoke') && ['active', 'pending'].includes(node.status) && (
                      <button type="button" className="v-btn danger"
                        title="Revoke access" aria-label="Revoke access"
                        onClick={() => setRevokeTarget(node)}>
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
            <div className="v-empty" style={{ padding: '2rem 1rem' }}>
              <div className="v-empty-icon"><Clock size={22} strokeWidth={1.5} /></div>
              <div className="v-empty-title">Nothing recorded yet</div>
              <p className="v-empty-body">
                Views, reveals, shares and rotations appear here as they happen.
              </p>
            </div>
          ) : (
            timeline.map((e) => (
              <div key={e.seq} className="v-event">
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
    <VaultModal title="Share credential" onClose={onClose}>
      <form onSubmit={submit} style={{ marginTop: '.8rem' }}>
        <label className="form-label" htmlFor="s-user"
          style={{ display: 'block' }}>User ID</label>
        <input id="s-user" className="form-input" required type="number"
          value={form.grantee_user_id}
          onChange={(e) => setForm({ ...form, grantee_user_id: e.target.value })}
          style={{ width: '100%', marginBottom: '.7rem' }} />

        <label className="form-label" htmlFor="s-perm"
          style={{ display: 'block' }}>Permission</label>
        <select id="s-perm" className="form-input form-select" value={form.permission}
          onChange={(e) => setForm({ ...form, permission: e.target.value })}
          style={{ width: '100%', marginBottom: '.4rem' }}>
          {LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
        </select>
        <div style={{ fontSize: '.72rem', color: 'var(--text3)', marginBottom: '.7rem',
          lineHeight: 1.5 }}>
          You cannot grant more than you hold. <code>reveal</code> lets them see
          the secret; <code>view</code> shows only that it exists.
        </div>

        <label className="form-label" htmlFor="s-exp"
          style={{ display: 'block' }}>Expires (optional)</label>
        <input id="s-exp" className="form-input" type="datetime-local"
          value={form.expires_at}
          onChange={(e) => setForm({ ...form, expires_at: e.target.value })}
          style={{ width: '100%' }} />
        <div style={{ fontSize: '.72rem', color: 'var(--text3)', marginTop: '.3rem' }}>
          Leave blank for access that does not expire.
        </div>

        <button type="submit" className="v-btn-primary"
          disabled={busy || !form.grantee_user_id}>
          {busy ? 'Sharing…' : 'Share'}
        </button>
      </form>
    </VaultModal>
  );
}
