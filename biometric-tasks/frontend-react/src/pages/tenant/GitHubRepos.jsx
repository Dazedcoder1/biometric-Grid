// src/pages/tenant/GitHubRepos.jsx
//
// Per-tenant GitHub repo configuration. The webhook secret is shown exactly
// once, right after the repo is added — the server stores it encrypted and
// cannot display it again.

import React, { useState, useEffect } from 'react';
import {
  CodeSquare as Github, Plus, RefreshCw, Trash2, AlertCircle, CheckCircle,
  Copy, X, Eye, EyeOff,
} from 'lucide-react';
import DashboardLayout from '../../layouts/DashboardLayout';
import ConfirmationModal from '../../components/ConfirmationModal';
import { tenantTaskApi } from '../../services/api';

const emptyForm = { full_name: '', token: '', label_filter: '', is_default: false, default_assignee_id: '' };

const GitHubRepos = () => {
  const [repos, setRepos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [showToken, setShowToken] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [syncing, setSyncing] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [justAdded, setJustAdded] = useState(null); // holds the one-time secret

  // GitHub login mapping — required for assignment to mirror onto issues
  const [mapping, setMapping] = useState([]);
  const [savingUser, setSavingUser] = useState(null);
  const [writeAccess, setWriteAccess] = useState({}); // repoId -> {can_write, reason}

  const flash = (msg) => {
    setSuccess(msg);
    setTimeout(() => setSuccess(''), 4000);
  };

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const list = await tenantTaskApi.listRepos();
      setRepos(list);
      // Check write scope per repo so a missing permission shows up here,
      // rather than as a failed push after someone has written a task.
      const checks = await Promise.all(
        list.map((r) =>
          tenantTaskApi.writeAccess(r.id)
            .then((w) => [r.id, w])
            .catch(() => [r.id, { can_write: false, reason: 'Could not check.' }])
        )
      );
      setWriteAccess(Object.fromEntries(checks));
    } catch (err) {
      setError(err.message || 'Failed to load repositories');
    } finally {
      setLoading(false);
    }
  };

  const loadMapping = async () => {
    try {
      setMapping(await tenantTaskApi.listUserMapping());
    } catch {
      setMapping([]);
    }
  };

  useEffect(() => { load(); loadMapping(); }, []);

  const saveMapping = async (userId, value) => {
    setSavingUser(userId);
    try {
      const updated = await tenantTaskApi.setUserMapping(userId, value);
      setMapping((prev) =>
        prev.map((u) => (u.id === userId ? { ...u, github_username: updated.github_username } : u))
      );
      flash('GitHub username saved');
    } catch (err) {
      setError(err.message || 'Failed to save username');
    } finally {
      setSavingUser(null);
    }
  };

  const handleAdd = async (e) => {
    e.preventDefault();
    if (!form.full_name.includes('/')) {
      setError("Repository must be in 'owner/repo' form");
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      const created = await tenantTaskApi.addRepo({
        full_name: form.full_name.trim(),
        token: form.token.trim() || null,
        label_filter: form.label_filter.trim() || null,
        is_default: form.is_default,
        default_assignee_id: form.default_assignee_id
          ? Number(form.default_assignee_id) : null,
      });
      setJustAdded(created);
      setForm(emptyForm);
      setShowForm(false);
      await load();
    } catch (err) {
      setError(err.message || 'Failed to add repository');
    } finally {
      setSubmitting(false);
    }
  };

  const handleSync = async (repo) => {
    setSyncing(repo.id);
    setError('');
    try {
      const result = await tenantTaskApi.syncRepo(repo.id);
      if (result.ok) {
        flash(`Synced ${result.synced} issue(s) from ${repo.full_name}`);
      } else {
        setError(result.error || 'Sync failed');
      }
      await load();
    } catch (err) {
      setError(err.message || 'Sync failed');
    } finally {
      setSyncing(null);
    }
  };

  const setDefault = async (repo) => {
    try {
      await tenantTaskApi.updateRepo(repo.id, { is_default: true });
      flash(`${repo.full_name} is now the default — new tasks go here.`);
      await load();
    } catch (err) {
      setError(err.message || 'Failed to set default');
    }
  };

  const clearDefault = async (repo) => {
    try {
      await tenantTaskApi.updateRepo(repo.id, { is_default: false });
      flash('Default cleared — new tasks stay local unless a repo is picked.');
      await load();
    } catch (err) {
      setError(err.message || 'Failed to clear default');
    }
  };

  const setDefaultAssignee = async (repo, userId) => {
    try {
      await tenantTaskApi.updateRepo(repo.id, {
        default_assignee_id: userId ? Number(userId) : null,
      });
      flash('Default assignee updated');
      await load();
    } catch (err) {
      setError(err.message || 'Failed to set default assignee');
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await tenantTaskApi.removeRepo(deleteTarget.id, false);
      flash('Repository removed. Mirrored tasks were kept.');
      setDeleteTarget(null);
      await load();
    } catch (err) {
      setError(err.message || 'Failed to remove');
      setDeleteTarget(null);
    }
  };

  const copy = (text) => navigator.clipboard?.writeText(text);

  return (
    <DashboardLayout
      title="GitHub Repositories"
      role="superadmin"
      label="Tenant Admin"
      abbr="TA"
      color="#a855f7"
      bgColor="rgba(168,85,247,0.15)"
    >
      {error && (
        <div className="card-box" style={{ borderColor: '#ef4444', marginBottom: '1rem', display: 'flex', gap: '.5rem', alignItems: 'center' }}>
          <AlertCircle size={16} color="#ef4444" /> <span>{error}</span>
        </div>
      )}
      {success && (
        <div className="card-box" style={{ borderColor: '#10b981', marginBottom: '1rem', display: 'flex', gap: '.5rem', alignItems: 'center' }}>
          <CheckCircle size={16} color="#10b981" /> <span>{success}</span>
        </div>
      )}

      {/* One-time webhook secret — cannot be recovered after this panel closes */}
      {justAdded && (
        <div className="card-box" style={{ borderColor: '#f59e0b', marginBottom: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <h4 style={{ margin: 0 }}>Finish setup on GitHub</h4>
            <button className="btn btn-ghost" onClick={() => setJustAdded(null)}><X size={15} /></button>
          </div>
          <p style={{ fontSize: '.85rem', opacity: .85 }}>
            Add a webhook in <strong>{justAdded.full_name}</strong> →
            Settings → Webhooks → Add webhook:
          </p>
          <ul style={{ fontSize: '.85rem', lineHeight: 1.7 }}>
            <li><strong>Payload URL:</strong> <code>https://YOUR-API-DOMAIN{justAdded.webhook_url_path}</code></li>
            <li><strong>Content type:</strong> <code>application/json</code></li>
            <li>
              <strong>Secret:</strong>{' '}
              <code style={{ userSelect: 'all' }}>{justAdded.webhook_secret}</code>{' '}
              <button className="btn btn-ghost" onClick={() => copy(justAdded.webhook_secret)}>
                <Copy size={13} />
              </button>
            </li>
            <li><strong>Events:</strong> "Let me select individual events" → <em>Issues</em></li>
          </ul>
          <p style={{ fontSize: '.8rem', color: '#f59e0b' }}>
            This secret is shown once and stored encrypted — copy it now.
          </p>
          {justAdded.initial_sync && (
            <p style={{ fontSize: '.8rem', opacity: .8 }}>
              Initial sync: {justAdded.initial_sync.ok
                ? `${justAdded.initial_sync.synced} issue(s) imported.`
                : `failed — ${justAdded.initial_sync.error}`}
            </p>
          )}
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem' }}>
          <Github size={18} />
          <span style={{ opacity: .8 }}>{repos.length} repository(ies) connected</span>
        </div>
        <div style={{ display: 'flex', gap: '.5rem' }}>
          <button className="btn btn-ghost" onClick={load}><RefreshCw size={15} /></button>
          <button className="btn btn-teal" onClick={() => setShowForm((v) => !v)}>
            {showForm ? <X size={15} /> : <Plus size={15} />}
            {showForm ? ' Cancel' : ' Add Repository'}
          </button>
        </div>
      </div>

      {showForm && (
        <form className="card-box" style={{ marginBottom: '1rem' }} onSubmit={handleAdd}>
          <div className="form-group">
            <label className="form-label">Repository *</label>
            <input className="form-input" placeholder="owner/repo"
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
          </div>

          <div className="form-group">
            <label className="form-label">Personal access token</label>
            <div style={{ display: 'flex', gap: '.4rem' }}>
              <input
                className="form-input"
                type={showToken ? 'text' : 'password'}
                placeholder="ghp_… (required for private repos)"
                value={form.token}
                onChange={(e) => setForm({ ...form, token: e.target.value })}
                style={{ flex: 1 }}
                autoComplete="off"
              />
              <button type="button" className="btn btn-ghost" onClick={() => setShowToken((v) => !v)}>
                {showToken ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
            <small style={{ opacity: .7 }}>
              Needs read access to issues only. Stored encrypted; never shown again.
            </small>
          </div>

          <div className="form-group">
            <label className="form-label">Label filter</label>
            <input className="form-input" placeholder="e.g. bug,backend — leave blank for all issues"
              value={form.label_filter}
              onChange={(e) => setForm({ ...form, label_filter: e.target.value })} />
          </div>

          <div className="form-group">
            <label className="form-label">Default assignee</label>
            <select className="form-input" value={form.default_assignee_id}
              onChange={(e) => setForm({ ...form, default_assignee_id: e.target.value })}>
              <option value="">None</option>
              {mapping.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}{u.github_username ? ` (@${u.github_username})` : ' — no GitHub username'}
                </option>
              ))}
            </select>
            <small style={{ opacity: .7 }}>
              Used on issues whose task has nobody assigned.
            </small>
          </div>

          <div className="form-group">
            <label style={{ display: 'flex', alignItems: 'center', gap: '.5rem', cursor: 'pointer' }}>
              <input type="checkbox" checked={form.is_default}
                onChange={(e) => setForm({ ...form, is_default: e.target.checked })} />
              <span>Make this the default repository</span>
            </label>
            <small style={{ opacity: .7 }}>
              Every new task is opened here automatically. Only one repo can be
              the default; setting this clears any existing one.
            </small>
          </div>

          <button className="btn btn-teal" type="submit" disabled={submitting}>
            {submitting ? 'Verifying with GitHub…' : 'Add Repository'}
          </button>
        </form>
      )}

      {loading ? (
        <div className="card-box">Loading…</div>
      ) : repos.length === 0 ? (
        <div className="card-box" style={{ textAlign: 'center', padding: '2rem' }}>
          <Github size={32} style={{ opacity: .4 }} />
          <p>No repositories connected yet. Add one to start mirroring issues as tasks.</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: '.75rem' }}>
          {repos.map((r) => (
            <div key={r.id} className="card-box">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '.4rem', fontWeight: 600 }}>
                    <Github size={15} /> {r.full_name}
                    {r.is_default && (
                      <span style={{
                        fontSize: '.66rem', textTransform: 'uppercase', letterSpacing: '.04em',
                        border: '1px solid #10b981', color: '#10b981',
                        borderRadius: '999px', padding: '.05rem .45rem',
                      }}>default</span>
                    )}
                    {!r.is_active && <span style={{ fontSize: '.7rem', opacity: .6 }}>(inactive)</span>}
                  </div>
                  <div style={{ fontSize: '.78rem', opacity: .75, marginTop: '.3rem' }}>
                    {r.task_count} task(s) ·{' '}
                    {r.has_token ? 'token set' : 'no token (public only)'} ·{' '}
                    {writeAccess[r.id]
                      ? (writeAccess[r.id].can_write
                          ? 'can write issues'
                          : 'READ-ONLY token')
                      : 'checking write access…'} ·{' '}
                    {r.has_webhook_secret ? 'webhook configured' : 'no webhook secret'}
                    {r.label_filter && ` · labels: ${r.label_filter}`}
                  </div>
                  <div style={{ fontSize: '.75rem', opacity: .6, marginTop: '.2rem' }}>
                    Last synced:{' '}
                    {r.last_synced_at ? new Date(r.last_synced_at).toLocaleString() : 'never'}
                  </div>
                  {writeAccess[r.id] && !writeAccess[r.id].can_write && (
                    <div style={{ fontSize: '.75rem', color: '#f59e0b', marginTop: '.25rem' }}>
                      Tasks pushed to this repo will fail: {writeAccess[r.id].reason}
                    </div>
                  )}
                  {r.last_sync_error && (
                    <div style={{ fontSize: '.75rem', color: '#ef4444', marginTop: '.25rem' }}>
                      Last sync error: {r.last_sync_error}
                    </div>
                  )}

                  <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem',
                                marginTop: '.5rem', flexWrap: 'wrap' }}>
                    {r.is_default ? (
                      <button className="btn btn-ghost" style={{ fontSize: '.75rem' }}
                        onClick={() => clearDefault(r)}>
                        Stop being default
                      </button>
                    ) : (
                      <button className="btn btn-ghost" style={{ fontSize: '.75rem' }}
                        disabled={!r.is_active}
                        onClick={() => setDefault(r)}
                        title={r.is_active ? '' : 'Reactivate the repo first'}>
                        Make default
                      </button>
                    )}

                    <label style={{ fontSize: '.75rem', opacity: .8 }}>Default assignee:</label>
                    <select
                      className="form-input"
                      style={{ width: 'auto', padding: '.15rem .4rem', fontSize: '.78rem' }}
                      value={r.default_assignee_id || ''}
                      onChange={(e) => setDefaultAssignee(r, e.target.value)}
                    >
                      <option value="">None</option>
                      {mapping.map((u) => (
                        <option key={u.id} value={u.id}>{u.name}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '.4rem', whiteSpace: 'nowrap' }}>
                  <button className="btn btn-ghost" disabled={syncing === r.id}
                    onClick={() => handleSync(r)} title="Sync now">
                    <RefreshCw size={14} /> {syncing === r.id ? 'Syncing…' : 'Sync'}
                  </button>
                  <button className="btn btn-red" onClick={() => setDeleteTarget(r)} title="Remove">
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ─── GitHub username mapping ─────────────────────────── */}
      <div className="card-box" style={{ marginTop: '1.5rem' }}>
        <h4 style={{ margin: '0 0 .35rem' }}>GitHub usernames</h4>
        <p style={{ fontSize: '.82rem', opacity: .75, marginTop: 0 }}>
          GitHub can't resolve your users, so assigning a task only mirrors onto
          the issue when that person's GitHub login is set here. Users without
          one still get the task — the issue is just left unassigned.
        </p>

        {mapping.length === 0 ? (
          <div style={{ opacity: .6, fontSize: '.85rem' }}>No users found.</div>
        ) : (
          <div className="table-wrap">
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left', padding: '.5rem' }}>User</th>
                  <th style={{ textAlign: 'left', padding: '.5rem' }}>Role</th>
                  <th style={{ textAlign: 'left', padding: '.5rem' }}>GitHub username</th>
                </tr>
              </thead>
              <tbody>
                {mapping.map((u) => (
                  <tr key={u.id} style={{ borderTop: '1px solid rgba(128,128,128,.18)' }}>
                    <td style={{ padding: '.5rem' }}>
                      {u.name}
                      <div style={{ fontSize: '.75rem', opacity: .6 }}>{u.email}</div>
                    </td>
                    <td style={{ padding: '.5rem', fontSize: '.8rem', opacity: .8 }}>{u.role}</td>
                    <td style={{ padding: '.5rem' }}>
                      <input
                        className="form-input"
                        placeholder="octocat"
                        defaultValue={u.github_username || ''}
                        disabled={savingUser === u.id}
                        onBlur={(e) => {
                          const v = e.target.value.trim();
                          if (v !== (u.github_username || '')) saveMapping(u.id, v);
                        }}
                        onKeyDown={(e) => e.key === 'Enter' && e.target.blur()}
                        style={{ width: '180px', padding: '.25rem .45rem' }}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <ConfirmationModal
        isOpen={!!deleteTarget}
        title="Remove repository"
        message={`Stop mirroring ${deleteTarget?.full_name}? Tasks already imported are kept, but will no longer update.`}
        confirmText="Remove"
        type="danger"
        onConfirm={handleDelete}
        onClose={() => setDeleteTarget(null)}
      />
    </DashboardLayout>
  );
};

export default GitHubRepos;
