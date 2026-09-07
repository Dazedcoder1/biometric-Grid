// src/components/TaskBoard.jsx
//
// Shared task UI for all three roles. The role differences are passed in as
// capabilities rather than branched on inside, so tenant/org/employee pages
// stay thin and can't drift apart.
//
//   api          - one of tenantTaskApi / orgTaskApi / employeeTaskApi
//   canCreate    - show the "New Task" form
//   canAssign    - show assignee/department/priority controls
//   canDelete    - show the delete action
//   readOnlyMeta - employee mode: status is the only editable field

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Plus, Search, RefreshCw, AlertCircle, Trash2, X, CodeSquare as Github,
  MessageSquare, Calendar, User as UserIcon, Send, ExternalLink,
} from 'lucide-react';
import ConfirmationModal from './ConfirmationModal';

const STATUSES = [
  { value: 'todo', label: 'To Do' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'in_review', label: 'In Review' },
  { value: 'done', label: 'Done' },
];

const PRIORITIES = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'urgent', label: 'Urgent' },
];

const PRIORITY_COLOR = {
  low: '#6b7585',
  medium: '#3b82f6',
  high: '#f59e0b',
  urgent: '#ef4444',
};

const STATUS_COLOR = {
  todo: '#6b7585',
  in_progress: '#3b82f6',
  in_review: '#a855f7',
  done: '#10b981',
};

const emptyForm = {
  title: '',
  description: '',
  priority: 'medium',
  status: 'todo',
  assigned_to: '',
  dept_id: '',
  due_date: '',
  github_repo_id: '',   // blank = task stays local
};

const TaskBoard = ({
  api,
  canCreate = false,
  canAssign = false,
  canDelete = false,
  readOnlyMeta = false,
}) => {
  const [tasks, setTasks] = useState([]);
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [repos, setRepos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const [filters, setFilters] = useState({ status: '', priority: '', source: '', search: '' });
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [submitting, setSubmitting] = useState(false);

  const [openTask, setOpenTask] = useState(null);
  const [comments, setComments] = useState([]);
  const [newComment, setNewComment] = useState('');
  const [deleteTarget, setDeleteTarget] = useState(null);

  // Inline GitHub connection, so the Tasks page isn't a dead end when no repo
  // is wired up yet. Only tenant admin has the add-repo endpoint.
  const canManageRepos = Boolean(api.addRepo);
  const [showConnect, setShowConnect] = useState(false);
  const [connectForm, setConnectForm] = useState({ full_name: '', token: '', is_default: true });
  const [connecting, setConnecting] = useState(false);
  const [connected, setConnected] = useState(null);   // one-time webhook secret
  const [syncing, setSyncing] = useState(false);
  const [lastSync, setLastSync] = useState(null);
  const autoSynced = useRef(false);

  const flash = (msg) => {
    setSuccess(msg);
    setTimeout(() => setSuccess(''), 3000);
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [taskData, statData] = await Promise.all([
        api.list(filters),
        api.stats(),
      ]);
      setTasks(taskData?.tasks || []);
      setStats(statData || null);
    } catch (err) {
      setError(err.message || 'Failed to load tasks');
    } finally {
      setLoading(false);
    }
  }, [api, filters]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!canAssign || !api.assignableUsers) return;
    api.assignableUsers().then(setUsers).catch(() => setUsers([]));
  }, [api, canAssign]);

  const loadRepos = useCallback(async () => {
    if (!api.pushableRepos) return;
    try {
      const list = await api.pushableRepos();
      setRepos(list);
      // Preselect the tenant's default so the common case needs no choice.
      const def = list.find((r) => r.is_default);
      if (def) setForm((f) => ({ ...f, github_repo_id: String(def.id) }));
    } catch {
      setRepos([]);
    }
  }, [api]);

  useEffect(() => {
    if (!canCreate) return;
    loadRepos();
  }, [canCreate, loadRepos]);

  const syncFromGitHub = useCallback(async (silent = false) => {
    if (!api.syncAll) return;
    setSyncing(true);
    if (!silent) setError('');
    try {
      const res = await api.syncAll();
      setLastSync(new Date());
      const failed = (res.results || []).filter((r) => !r.ok);
      if (failed.length && !silent) {
        setError(`GitHub sync failed for ${failed.map((f) => f.repo).join(', ')}: ${failed[0].error}`);
      } else if (!silent) {
        flash(`Pulled ${res.synced} issue(s) from ${res.repos} repo(s)`);
      }
      await load();
    } catch (err) {
      if (!silent) setError(err.message || 'Sync failed');
    } finally {
      setSyncing(false);
    }
  }, [api, load]);

  // Pull once when the page opens, quietly and after the tasks are already on
  // screen. Webhooks are the fast path, but they can't reach a server running
  // on localhost, so without this an issue filed on GitHub would not appear
  // until the background reconcile ran.
  useEffect(() => {
    if (autoSynced.current || !api.syncAll || repos.length === 0) return;
    autoSynced.current = true;
    syncFromGitHub(true);
  }, [api, repos.length, syncFromGitHub]);

  const connectRepo = async (e) => {
    e.preventDefault();
    if (!connectForm.full_name.includes('/')) {
      setError("Repository must be in 'owner/repo' form");
      return;
    }
    setConnecting(true);
    setError('');
    try {
      const created = await api.addRepo({
        full_name: connectForm.full_name.trim(),
        token: connectForm.token.trim() || null,
        is_default: connectForm.is_default,
      });
      setConnected(created);
      setConnectForm({ full_name: '', token: '', is_default: true });
      setShowConnect(false);
      await loadRepos();
      flash(`Connected ${created.full_name}`);
    } catch (err) {
      setError(err.message || 'Could not connect that repository');
    } finally {
      setConnecting(false);
    }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!form.title.trim()) {
      setError('Title is required');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      // Empty selects come through as '' — the API expects null or a number.
      const payload = {
        ...form,
        assigned_to: form.assigned_to ? Number(form.assigned_to) : null,
        dept_id: form.dept_id ? Number(form.dept_id) : null,
        due_date: form.due_date || null,
        github_repo_id: form.github_repo_id ? Number(form.github_repo_id) : null,
        // Without this, an empty picker would silently inherit the default repo.
        keep_local: !form.github_repo_id,
      };
      const created = await api.create(payload);
      const def = repos.find((r) => r.is_default);
      setForm({ ...emptyForm, github_repo_id: def ? String(def.id) : '' });
      setShowForm(false);
      // The task always saves; GitHub is best-effort, so surface a partial
      // failure rather than reporting plain success.
      if (created?.github_warning) {
        setError(created.github_warning);
        flash('Task created (see note above)');
      } else if (created?.github_issue_number) {
        flash(`Task created and opened as issue #${created.github_issue_number}`);
      } else {
        flash('Task created');
      }
      await load();
    } catch (err) {
      setError(err.message || 'Failed to create task');
    } finally {
      setSubmitting(false);
    }
  };

  const changeStatus = async (task, status) => {
    try {
      const res = readOnlyMeta
        ? await api.setStatus(task.id, status)
        : await api.update(task.id, { status });
      if (res?.github_warning) setError(res.github_warning);
      setTasks((prev) => prev.map((t) => (t.id === task.id ? { ...t, status } : t)));
      const fresh = await api.stats();
      setStats(fresh);
    } catch (err) {
      setError(err.message || 'Failed to update status');
    }
  };

  const changeAssignee = async (task, userId) => {
    try {
      const updated = await api.update(task.id, {
        assigned_to: userId ? Number(userId) : null,
      });
      setTasks((prev) => prev.map((t) => (t.id === task.id ? updated : t)));
      if (updated?.github_warning) setError(updated.github_warning);
      else flash('Assignment updated');
    } catch (err) {
      setError(err.message || 'Failed to reassign');
    }
  };

  const openDetail = async (task) => {
    setOpenTask(task);
    setComments([]);
    try {
      setComments(await api.comments(task.id));
    } catch {
      setComments([]);
    }
  };

  const postComment = async () => {
    if (!newComment.trim() || !openTask) return;
    try {
      const created = await api.addComment(openTask.id, newComment.trim());
      setComments((prev) => [...prev, created]);
      setNewComment('');
      if (created?.github_warning) setError(created.github_warning);
    } catch (err) {
      setError(err.message || 'Failed to post comment');
    }
  };

  const pushToGitHub = async (task) => {
    if (!api.push) return;
    try {
      const updated = await api.push(task.id, null);   // null = default repo
      setTasks((prev) => prev.map((t) => (t.id === task.id ? updated : t)));
      if (updated?.github_warning) setError(updated.github_warning);
      else flash(`Opened issue #${updated.github_issue_number}`);
    } catch (err) {
      setError(err.message || 'Failed to push to GitHub');
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      await api.remove(deleteTarget.id);
      setDeleteTarget(null);
      flash('Task deleted');
      await load();
    } catch (err) {
      setError(err.message || 'Failed to delete');
      setDeleteTarget(null);
    }
  };

  return (
    <>
      {/* ─── Stats ─────────────────────────────────────────────── */}
      {stats && (
        <div className="stats-grid" style={{ marginBottom: '1.25rem' }}>
          <div className="stat-card blue">
            <div className="stat-label">Total</div>
            <div className="stat-value">{stats.total ?? 0}</div>
          </div>
          <div className="stat-card teal">
            <div className="stat-label">To Do</div>
            <div className="stat-value">{stats.todo ?? 0}</div>
          </div>
          <div className="stat-card purple">
            <div className="stat-label">In Progress</div>
            <div className="stat-value">{stats.in_progress ?? 0}</div>
          </div>
          <div className="stat-card green">
            <div className="stat-label">Done</div>
            <div className="stat-value">{stats.done ?? 0}</div>
          </div>
        </div>
      )}

      {/* ─── Messages ──────────────────────────────────────────── */}
      {error && (
        <div className="card-box" style={{ borderColor: '#ef4444', marginBottom: '1rem', display: 'flex', gap: '.5rem', alignItems: 'center' }}>
          <AlertCircle size={16} color="#ef4444" />
          <span>{error}</span>
        </div>
      )}
      {success && (
        <div className="card-box" style={{ borderColor: '#10b981', marginBottom: '1rem' }}>
          {success}
        </div>
      )}

      {/* ─── GitHub connection ─────────────────────────────────── */}
      {canCreate && (
        <div className="card-box" style={{ marginBottom: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '.6rem', flexWrap: 'wrap' }}>
            <Github size={16} />

            {repos.length === 0 ? (
              <>
                <span style={{ opacity: .8, fontSize: '.88rem' }}>
                  No GitHub repository connected — tasks stay in this app only.
                </span>
                {canManageRepos ? (
                  <button className="btn btn-teal" style={{ marginLeft: 'auto' }}
                    onClick={() => setShowConnect((v) => !v)}>
                    {showConnect ? <X size={14} /> : <Plus size={14} />}
                    {showConnect ? ' Cancel' : ' Connect GitHub'}
                  </button>
                ) : (
                  <span style={{ marginLeft: 'auto', fontSize: '.8rem', opacity: .7 }}>
                    Ask your tenant admin to connect one.
                  </span>
                )}
              </>
            ) : (
              <>
                <span style={{ opacity: .85, fontSize: '.88rem' }}>
                  New tasks go to:
                </span>
                <select
                  className="form-input"
                  style={{ width: 'auto' }}
                  value={form.github_repo_id}
                  onChange={(e) => setForm({ ...form, github_repo_id: e.target.value })}
                >
                  <option value="">Keep local only (no issue)</option>
                  {repos.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.full_name}{r.is_default ? '  (default)' : ''}
                    </option>
                  ))}
                </select>

                <span style={{ fontSize: '.78rem', opacity: .65 }}>
                  {form.github_repo_id
                    ? 'Each new task opens a real issue there.'
                    : 'Nothing is sent to GitHub.'}
                </span>

                <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '.5rem' }}>
                  {lastSync && (
                    <span style={{ fontSize: '.72rem', opacity: .6 }}>
                      synced {lastSync.toLocaleTimeString()}
                    </span>
                  )}
                  <button className="btn btn-ghost" disabled={syncing}
                    onClick={() => syncFromGitHub(false)}
                    title="Pull issues created or changed on GitHub">
                    <RefreshCw size={14} />{syncing ? ' Syncing…' : ' Sync from GitHub'}
                  </button>
                  {canManageRepos && (
                    <button className="btn btn-ghost" onClick={() => setShowConnect((v) => !v)}>
                      {showConnect ? <X size={14} /> : <Plus size={14} />}
                      {showConnect ? ' Cancel' : ' Add repo'}
                    </button>
                  )}
                </div>
              </>
            )}
          </div>

          {/* Inline connect form */}
          {canManageRepos && showConnect && (
            <form onSubmit={connectRepo} style={{ marginTop: '.9rem' }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '.75rem' }}>
                <div className="form-group">
                  <label className="form-label">Repository *</label>
                  <input className="form-input" placeholder="owner/repo"
                    value={connectForm.full_name}
                    onChange={(e) => setConnectForm({ ...connectForm, full_name: e.target.value })} />
                </div>
                <div className="form-group">
                  <label className="form-label">Personal access token</label>
                  <input className="form-input" type="password" autoComplete="off"
                    placeholder="ghp_… (needs Issues: read and write)"
                    value={connectForm.token}
                    onChange={(e) => setConnectForm({ ...connectForm, token: e.target.value })} />
                </div>
              </div>
              <label style={{ display: 'flex', alignItems: 'center', gap: '.5rem',
                              fontSize: '.85rem', cursor: 'pointer', marginBottom: '.6rem' }}>
                <input type="checkbox" checked={connectForm.is_default}
                  onChange={(e) => setConnectForm({ ...connectForm, is_default: e.target.checked })} />
                Make this the default for new tasks
              </label>
              <button className="btn btn-teal" type="submit" disabled={connecting}>
                {connecting ? 'Verifying with GitHub…' : 'Connect'}
              </button>
              <small style={{ display: 'block', marginTop: '.5rem', opacity: .7 }}>
                The token is verified against GitHub and stored encrypted. Existing
                issues in the repo are imported as tasks straight away.
              </small>
            </form>
          )}

          {/* Webhook secret — shown once, never recoverable */}
          {connected?.webhook_secret && (
            <div style={{ marginTop: '.9rem', paddingTop: '.75rem',
                          borderTop: '1px solid rgba(128,128,128,.2)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <strong style={{ fontSize: '.85rem' }}>
                  Optional: finish webhook setup on GitHub
                </strong>
                <button className="btn btn-ghost" onClick={() => setConnected(null)}>
                  <X size={14} />
                </button>
              </div>
              <div style={{ fontSize: '.8rem', opacity: .85, lineHeight: 1.6 }}>
                In <strong>{connected.full_name}</strong> → Settings → Webhooks → Add webhook.
                Payload URL <code>https://YOUR-API-DOMAIN/api/webhooks/github</code>,
                content type <code>application/json</code>, events <em>Issues</em> and
                <em> Issue comments</em>. Secret (shown once):
                <br />
                <code style={{ userSelect: 'all' }}>{connected.webhook_secret}</code>
              </div>
              {connected.initial_sync && (
                <div style={{ fontSize: '.78rem', opacity: .75, marginTop: '.35rem' }}>
                  {connected.initial_sync.ok
                    ? `Imported ${connected.initial_sync.synced} existing issue(s).`
                    : `Initial import failed — ${connected.initial_sync.error}`}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ─── Toolbar ───────────────────────────────────────────── */}
      <div className="card-box" style={{ marginBottom: '1rem', display: 'flex', gap: '.75rem', flexWrap: 'wrap', alignItems: 'center' }}>
        <div className="input-wrap" style={{ flex: '1 1 220px', display: 'flex', alignItems: 'center', gap: '.4rem' }}>
          <Search size={15} />
          <input
            className="form-input"
            placeholder="Search tasks…"
            value={filters.search}
            onChange={(e) => setFilters({ ...filters, search: e.target.value })}
            style={{ border: 'none', background: 'transparent', flex: 1 }}
          />
        </div>

        <select className="form-input" style={{ width: 'auto' }} value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value })}>
          <option value="">All statuses</option>
          {STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>

        <select className="form-input" style={{ width: 'auto' }} value={filters.priority}
          onChange={(e) => setFilters({ ...filters, priority: e.target.value })}>
          <option value="">All priorities</option>
          {PRIORITIES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>

        <select className="form-input" style={{ width: 'auto' }} value={filters.source}
          onChange={(e) => setFilters({ ...filters, source: e.target.value })}>
          <option value="">All sources</option>
          <option value="manual">Manual</option>
          <option value="github">GitHub</option>
        </select>

        <button className="btn btn-ghost" onClick={load} title="Refresh">
          <RefreshCw size={15} />
        </button>

        {canCreate && (
          <button className="btn btn-teal" onClick={() => setShowForm((v) => !v)}>
            {showForm ? <X size={15} /> : <Plus size={15} />}
            {showForm ? ' Cancel' : ' New Task'}
          </button>
        )}
      </div>

      {/* ─── Create form ───────────────────────────────────────── */}
      {canCreate && showForm && (
        <form className="card-box" style={{ marginBottom: '1rem' }} onSubmit={handleCreate}>
          <div className="form-group">
            <label className="form-label">Title *</label>
            <input className="form-input" value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="What needs doing?" />
          </div>

          <div className="form-group">
            <label className="form-label">Description</label>
            <textarea className="form-input" rows={3} value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '.75rem' }}>
            <div className="form-group">
              <label className="form-label">Priority</label>
              <select className="form-input" value={form.priority}
                onChange={(e) => setForm({ ...form, priority: e.target.value })}>
                {PRIORITIES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Status</label>
              <select className="form-input" value={form.status}
                onChange={(e) => setForm({ ...form, status: e.target.value })}>
                {STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
            </div>

            {canAssign && (
              <div className="form-group">
                <label className="form-label">Assign to</label>
                <select className="form-input" value={form.assigned_to}
                  onChange={(e) => setForm({ ...form, assigned_to: e.target.value })}>
                  <option value="">Unassigned</option>
                  {users.map((u) => (
                    <option key={u.id} value={u.id}>{u.name} ({u.role})</option>
                  ))}
                </select>
              </div>
            )}

            <div className="form-group">
              <label className="form-label">Due date</label>
              <input type="date" className="form-input" value={form.due_date}
                onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
            </div>

            {/* Repo choice lives in the GitHub bar above, so it's visible
                without opening this form. Repeated here only as a reminder. */}
            {repos.length > 0 && (
              <div className="form-group">
                <label className="form-label">Destination</label>
                <div className="form-input" style={{ opacity: .8, cursor: 'default' }}>
                  {form.github_repo_id
                    ? (repos.find((r) => String(r.id) === String(form.github_repo_id))?.full_name
                       || 'Selected repository')
                    : 'Local only — no GitHub issue'}
                </div>
                <small style={{ opacity: .7 }}>Change this in the GitHub bar above.</small>
              </div>
            )}
          </div>

          <button className="btn btn-teal" type="submit" disabled={submitting}>
            {submitting ? 'Creating…' : 'Create Task'}
          </button>
        </form>
      )}

      {/* ─── List ──────────────────────────────────────────────── */}
      {loading ? (
        <div className="card-box">Loading tasks…</div>
      ) : tasks.length === 0 ? (
        <div className="card-box" style={{ textAlign: 'center', padding: '2rem' }}>
          No tasks match these filters.
        </div>
      ) : (
        <div className="table-wrap">
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', padding: '.6rem' }}>Task</th>
                <th style={{ textAlign: 'left', padding: '.6rem' }}>Priority</th>
                <th style={{ textAlign: 'left', padding: '.6rem' }}>Status</th>
                {canAssign && <th style={{ textAlign: 'left', padding: '.6rem' }}>Assignee</th>}
                <th style={{ textAlign: 'left', padding: '.6rem' }}>Due</th>
                <th style={{ textAlign: 'right', padding: '.6rem' }}></th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((t) => (
                <tr key={t.id} style={{ borderTop: '1px solid rgba(128,128,128,.18)' }}>
                  <td style={{ padding: '.6rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '.4rem' }}>
                      {t.source === 'github' && <Github size={14} />}
                      <button
                        onClick={() => openDetail(t)}
                        style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: 'inherit', font: 'inherit', textAlign: 'left' }}
                      >
                        {t.title}
                      </button>
                    </div>
                    {t.github_repo && (
                      <div style={{ fontSize: '.75rem', opacity: .65, marginTop: '.15rem' }}>
                        {t.github_repo}#{t.github_issue_number}
                      </div>
                    )}
                  </td>

                  <td style={{ padding: '.6rem' }}>
                    <span style={{
                      color: PRIORITY_COLOR[t.priority],
                      border: `1px solid ${PRIORITY_COLOR[t.priority]}`,
                      borderRadius: '999px', padding: '.1rem .5rem', fontSize: '.72rem',
                    }}>
                      {t.priority}
                    </span>
                  </td>

                  <td style={{ padding: '.6rem' }}>
                    <select
                      value={t.status}
                      onChange={(e) => changeStatus(t, e.target.value)}
                      className="form-input"
                      style={{ width: 'auto', padding: '.2rem .4rem', color: STATUS_COLOR[t.status] }}
                    >
                      {STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                    </select>
                  </td>

                  {canAssign && (
                    <td style={{ padding: '.6rem' }}>
                      <select
                        className="form-input"
                        style={{ width: 'auto', padding: '.2rem .4rem' }}
                        value={t.assigned_to || ''}
                        onChange={(e) => changeAssignee(t, e.target.value)}
                      >
                        <option value="">Unassigned</option>
                        {users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
                      </select>
                    </td>
                  )}

                  <td style={{ padding: '.6rem', fontSize: '.8rem', opacity: .8 }}>
                    {t.due_date ? new Date(t.due_date).toLocaleDateString() : '—'}
                  </td>

                  <td style={{ padding: '.6rem', textAlign: 'right', whiteSpace: 'nowrap' }}>
                    {t.github_url && (
                      <a href={t.github_url} target="_blank" rel="noopener noreferrer"
                        className="btn btn-ghost" style={{ marginRight: '.3rem' }} title="Open on GitHub">
                        <Github size={14} />
                      </a>
                    )}
                    {canCreate && api.push && !t.github_issue_number && (
                      <button className="btn btn-ghost" style={{ marginRight: '.3rem' }}
                        onClick={() => pushToGitHub(t)}
                        title="Open this task as a GitHub issue">
                        <Github size={14} />+
                      </button>
                    )}
                    {canDelete && t.source !== 'github' && (
                      <button className="btn btn-red" onClick={() => setDeleteTarget(t)} title="Delete">
                        <Trash2 size={14} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ─── Detail drawer ─────────────────────────────────────── */}
      {openTask && (
        <div
          onClick={() => setOpenTask(null)}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)',
            display: 'flex', justifyContent: 'flex-end', zIndex: 60,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: 'min(520px, 100%)', height: '100%', overflowY: 'auto',
              background: 'var(--card, #12161f)', padding: '1.25rem',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem' }}>
              <h3 style={{ margin: 0 }}>{openTask.title}</h3>
              <button className="btn btn-ghost" onClick={() => setOpenTask(null)}><X size={16} /></button>
            </div>

            <div style={{ display: 'flex', gap: '.4rem', flexWrap: 'wrap', margin: '.75rem 0' }}>
              <span style={{ fontSize: '.72rem', color: PRIORITY_COLOR[openTask.priority] }}>
                {openTask.priority}
              </span>
              <span style={{ fontSize: '.72rem', color: STATUS_COLOR[openTask.status] }}>
                · {openTask.status}
              </span>
              {openTask.source === 'github' && (
                <span style={{ fontSize: '.72rem', opacity: .7 }}>· mirrored from GitHub</span>
              )}
            </div>

            {openTask.assignee_name && (
              <div style={{ fontSize: '.8rem', opacity: .8, display: 'flex', alignItems: 'center', gap: '.35rem' }}>
                <UserIcon size={13} /> {openTask.assignee_name}
              </div>
            )}
            {openTask.due_date && (
              <div style={{ fontSize: '.8rem', opacity: .8, display: 'flex', alignItems: 'center', gap: '.35rem' }}>
                <Calendar size={13} /> Due {new Date(openTask.due_date).toLocaleDateString()}
              </div>
            )}

            {openTask.description && (
              <p style={{ whiteSpace: 'pre-wrap', marginTop: '1rem', fontSize: '.88rem', lineHeight: 1.55 }}>
                {openTask.description}
              </p>
            )}

            {openTask.github_url && (
              <a href={openTask.github_url} target="_blank" rel="noopener noreferrer"
                className="btn btn-ghost" style={{ marginTop: '.5rem' }}>
                <Github size={14} /> View issue on GitHub
              </a>
            )}

            <hr style={{ margin: '1.25rem 0', border: 0, borderTop: '1px solid rgba(128,128,128,.2)' }} />

            <h4 style={{ display: 'flex', alignItems: 'center', gap: '.4rem', margin: '0 0 .75rem' }}>
              <MessageSquare size={15} /> Comments
            </h4>

            {comments.length === 0 && (
              <div style={{ opacity: .6, fontSize: '.85rem' }}>No comments yet.</div>
            )}
            {comments.map((c) => (
              <div key={c.id} style={{ marginBottom: '.75rem' }}>
                <div style={{ fontSize: '.75rem', opacity: .7 }}>
                  {c.author_name || 'Unknown'} · {c.created_at ? new Date(c.created_at).toLocaleString() : ''}
                </div>
                <div style={{ fontSize: '.88rem', whiteSpace: 'pre-wrap' }}>{c.body}</div>
              </div>
            ))}

            <div style={{ display: 'flex', gap: '.4rem', marginTop: '1rem' }}>
              <input
                className="form-input"
                placeholder="Add a comment…"
                value={newComment}
                onChange={(e) => setNewComment(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && postComment()}
                style={{ flex: 1 }}
              />
              <button className="btn btn-teal" onClick={postComment}><Send size={14} /></button>
            </div>
          </div>
        </div>
      )}

      <ConfirmationModal
        isOpen={!!deleteTarget}
        title="Delete task"
        message={`Delete "${deleteTarget?.title}"? This cannot be undone.`}
        onConfirm={confirmDelete}
        onClose={() => setDeleteTarget(null)}
        confirmText="Delete"
        type="danger"
      />
    </>
  );
};

export default TaskBoard;
