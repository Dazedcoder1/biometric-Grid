// src/pages/super/Organisations.jsx
//
// The platform screen: every organisation on this deployment, from above.
//
// Until now a Super Admin had no screen of their own. They landed on an
// organisation chooser whose empty state said to run create_organisation.py on
// the server — the create, rotate and delete endpoints existed, but nothing in
// the interface called them. This is where those live, and where a Super Admin
// starts after signing in.
//
// Two rules the page keeps:
//
//  * API keys are shown only at the moment they are issued — on creation and
//    on rotation — and never fetched again. The list carries the last four
//    characters, which is enough to tell keys apart and useless to anyone
//    reading over a shoulder or a screenshot.
//
//  * Deleting is offered only for an empty organisation, and the server
//    decides what empty means. When it is not, the dialog says exactly what is
//    still inside rather than greying out a button with no explanation.

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertCircle, AlertTriangle, ArrowRight, Building2, Check, Clock, Copy, Cpu,
  Eye, EyeOff, KeyRound, Pencil, Plus, RefreshCw, Search, ShieldCheck, Trash2,
  Users, Wand2,
} from 'lucide-react';

import DashboardLayout from '../../layouts/DashboardLayout';
import VaultModal from '../../components/VaultModal';
import {
  superAdminApi, setActingTenant, getActingTenantId, clearActingTenant,
} from '../../services/api';
import '../vault/vault.css';

// ─────────────────────────────────────────────────────────────────────────────
// Small helpers
// ─────────────────────────────────────────────────────────────────────────────

const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

function sinceText(iso) {
  if (!iso) return null;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;
  const mins = Math.floor((Date.now() - then) / 60_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' });
}

function shortDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? '—'
    : d.toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' });
}

function workingDays(csv) {
  const days = String(csv || '').split(',').map((n) => DAY_NAMES[Number(n) - 1]).filter(Boolean);
  return days.length ? days.join(', ') : '—';
}

function hhmm(t) {
  return t ? String(t).slice(0, 5) : '—';
}

/** Mirrors the server's rule so the form can say so before submitting. */
function passwordProblem(pw) {
  if (pw.length < 8) return 'At least 8 characters.';
  if (!/[A-Za-z]/.test(pw) || !/\d/.test(pw)) return 'Needs a letter and a number.';
  return '';
}

/** A readable, strong-enough password: no 0/O or 1/l to misread when handing it over. */
function generatePassword() {
  const letters = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz';
  const digits = '23456789';
  const all = letters + digits;
  const pick = (set) => {
    const buf = new Uint32Array(1);
    crypto.getRandomValues(buf);
    return set[buf[0] % set.length];
  };
  const chars = [pick(letters), pick(digits)];
  while (chars.length < 14) chars.push(pick(all));
  // Shuffle so the guaranteed letter and digit are not always first.
  for (let i = chars.length - 1; i > 0; i -= 1) {
    const buf = new Uint32Array(1);
    crypto.getRandomValues(buf);
    const j = buf[0] % (i + 1);
    [chars[i], chars[j]] = [chars[j], chars[i]];
  }
  return chars.join('');
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Older browsers, or a page not served over https: fall back to a
    // selection copy rather than failing silently.
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try { ok = document.execCommand('copy'); } catch { ok = false; }
    document.body.removeChild(ta);
    return ok;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Pieces
// ─────────────────────────────────────────────────────────────────────────────

/** A value shown once, with a copy button. Used for issued API keys. */
function RevealOnce({ label, value, note }) {
  const [copied, setCopied] = useState(false);
  return (
    <div style={{ marginTop: '.8rem' }}>
      <div className="form-label" style={{ marginBottom: '.35rem' }}>{label}</div>
      <div style={{ display: 'flex', gap: '.4rem', alignItems: 'stretch' }}>
        <code className="v-secret" style={{ flex: 1, minWidth: 0, overflowWrap: 'anywhere' }}>
          {value}
        </code>
        <button
          type="button"
          className="v-btn"
          onClick={async () => { setCopied(await copyText(value)); }}
          aria-label={`Copy ${label}`}
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      {note && (
        <div className="v-banner warn" style={{ marginTop: '.6rem', marginBottom: 0 }}>
          <AlertTriangle size={14} />
          <span>{note}</span>
        </div>
      )}
    </div>
  );
}

function Stat({ tone, label, value, sub }) {
  return (
    <div className={`stat-card ${tone}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value ?? '—'}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

function OrgCard({ org, active, onWorkIn, onManage }) {
  const s = org.stats || {};
  const people = (s.employees || 0) + (s.org_admins || 0) + (s.tenant_admins || 0);
  const last = sinceText(s.last_activity);

  return (
    <div
      className="card-box"
      style={{
        padding: '1.1rem 1.15rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '.8rem',
        borderColor: active ? 'var(--purple)' : undefined,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '.7rem' }}>
        <div
          className="v-kind"
          style={{ background: 'rgba(168,85,247,0.12)', color: 'var(--purple)', flexShrink: 0 }}
        >
          <Building2 size={17} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontWeight: 600, fontSize: '.98rem', color: 'var(--text)',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}
          >
            {org.name}
          </div>
          <div style={{ fontSize: '.74rem', color: 'var(--text3)', fontFamily: 'var(--mono)', marginTop: 2 }}>
            #{org.id} · since {shortDate(org.created_at)}
          </div>
        </div>
        {active && (
          <span className="v-chip info" title="Every tenant screen is currently scoped to this organisation">
            <Check size={11} /> Working in
          </span>
        )}
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '.35rem' }}>
        <span className="v-chip"><Users size={11} /> {people} {people === 1 ? 'person' : 'people'}</span>
        <span className="v-chip">{s.departments || 0} dept{s.departments === 1 ? '' : 's'}</span>
        <span className={`v-chip ${s.devices && s.devices_online === s.devices ? 'good' : ''}`}>
          <Cpu size={11} /> {s.devices_online || 0}/{s.devices || 0} online
        </span>
        <span className="v-chip" title="Last four characters of the organisation's API key">
          <KeyRound size={11} /> {org.api_key_hint || '—'}
        </span>
      </div>

      <div style={{ fontSize: '.78rem', color: 'var(--text3)', display: 'flex', alignItems: 'center', gap: 6 }}>
        <Clock size={12} />
        {last ? `Last attendance ${last}` : 'No attendance recorded yet'}
      </div>

      <div style={{ display: 'flex', gap: '.5rem', marginTop: 'auto' }}>
        <button type="button" className="btn btn-teal" style={{ flex: 1 }} onClick={() => onWorkIn(org)}>
          {active ? 'Open dashboard' : 'Work in this organisation'}
          <ArrowRight size={14} style={{ marginLeft: 6 }} />
        </button>
        <button type="button" className="btn btn-ghost" onClick={() => onManage(org)}>
          Manage
        </button>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Create
// ─────────────────────────────────────────────────────────────────────────────

const EMPTY_FORM = {
  name: '', department: 'General', admin_name: '', admin_email: '', admin_password: '',
};

function CreateOrganisationModal({ onClose, onCreated, onWorkIn }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [showPw, setShowPw] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [touched, setTouched] = useState(false);
  const [created, setCreated] = useState(null);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
  const pwIssue = passwordProblem(form.admin_password);
  const incomplete = !form.name.trim() || !form.admin_name.trim() || !form.admin_email.trim();

  const submit = async (e) => {
    e.preventDefault();
    setTouched(true);
    if (incomplete || pwIssue) return;
    setBusy(true);
    setError('');
    try {
      const res = await superAdminApi.createTenant({
        name: form.name.trim(),
        department: form.department.trim() || 'General',
        admin_name: form.admin_name.trim(),
        admin_email: form.admin_email.trim(),
        admin_password: form.admin_password,
      });
      setCreated(res);
      onCreated();
    } catch (err) {
      setError(err.message || 'The organisation could not be created.');
    } finally {
      setBusy(false);
    }
  };

  if (created) {
    return (
      <VaultModal title="Organisation ready" onClose={onClose}>
        <div className="v-banner ok" style={{ marginTop: '.6rem' }}>
          <ShieldCheck size={14} />
          <span>
            <strong>{created.tenant.name}</strong> is set up with a department, default office hours
            and a Tenant Admin who can sign in now.
          </span>
        </div>

        <div style={{ fontSize: '.85rem', color: 'var(--text2)', lineHeight: 1.6 }}>
          <div><span style={{ color: 'var(--text3)' }}>Tenant Admin:</span> {created.admin.name}</div>
          <div>
            <span style={{ color: 'var(--text3)' }}>Signs in with:</span>{' '}
            <code style={{ fontFamily: 'var(--mono)' }}>{created.admin.email}</code>{' '}
            and the password you set
          </div>
        </div>

        <RevealOnce
          label="API key"
          value={created.api_key}
          note="Copy this now — it is not shown again. It's for devices and integrations only; people sign in with email and password."
        />

        <div style={{ display: 'flex', gap: '.5rem', marginTop: '1.2rem' }}>
          <button type="button" className="btn btn-ghost" style={{ flex: 1 }} onClick={onClose}>
            Done
          </button>
          <button
            type="button"
            className="btn btn-teal"
            style={{ flex: 1 }}
            onClick={() => onWorkIn(created.tenant)}
          >
            Work in it now <ArrowRight size={14} style={{ marginLeft: 6 }} />
          </button>
        </div>
      </VaultModal>
    );
  }

  return (
    <VaultModal title="New organisation" onClose={onClose}>
      <p style={{ fontSize: '.82rem', color: 'var(--text3)', margin: '.2rem 0 1rem', lineHeight: 1.5 }}>
        Creates the organisation, its first department and default office hours, and a Tenant
        Admin who can sign in straight away.
      </p>

      {error && (
        <div className="v-banner bad" role="alert">
          <AlertCircle size={14} />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={submit} noValidate>
        <div className="form-group">
          <label className="form-label" htmlFor="org-name">Organisation name</label>
          <input
            id="org-name"
            className="form-input"
            value={form.name}
            onChange={set('name')}
            placeholder="Acme Industries"
            autoFocus
            maxLength={120}
          />
          {touched && !form.name.trim() && <div className="form-hint" style={{ color: 'var(--bad)' }}>Required.</div>}
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="org-dept">First department</label>
          <input
            id="org-dept"
            className="form-input"
            value={form.department}
            onChange={set('department')}
            maxLength={80}
          />
          <div className="form-hint">More can be added later from the organisation&apos;s Departments screen.</div>
        </div>

        <div className="section-title" style={{ margin: '1.1rem 0 .6rem', fontSize: '.8rem' }}>
          Tenant Admin
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="admin-name">Full name</label>
          <input
            id="admin-name"
            className="form-input"
            value={form.admin_name}
            onChange={set('admin_name')}
            placeholder="Priya Shah"
            maxLength={120}
          />
          {touched && !form.admin_name.trim() && <div className="form-hint" style={{ color: 'var(--bad)' }}>Required.</div>}
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="admin-email">Email</label>
          <input
            id="admin-email"
            type="email"
            className="form-input"
            value={form.admin_email}
            onChange={set('admin_email')}
            placeholder="priya@acme.com"
            autoComplete="off"
          />
          {touched && !form.admin_email.trim() && <div className="form-hint" style={{ color: 'var(--bad)' }}>Required.</div>}
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="admin-pw">Password</label>
          <div style={{ display: 'flex', gap: '.4rem' }}>
            <div style={{ position: 'relative', flex: 1 }}>
              <input
                id="admin-pw"
                type={showPw ? 'text' : 'password'}
                className="form-input"
                value={form.admin_password}
                onChange={set('admin_password')}
                autoComplete="new-password"
                style={{ width: '100%', paddingRight: 36, fontFamily: showPw ? 'var(--mono)' : undefined }}
              />
              <button
                type="button"
                onClick={() => setShowPw((v) => !v)}
                aria-label={showPw ? 'Hide password' : 'Show password'}
                style={{
                  position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)',
                  background: 'none', border: 'none', color: 'var(--text3)', cursor: 'pointer', padding: 4,
                }}
              >
                {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
            <button
              type="button"
              className="v-btn"
              onClick={() => { setForm((f) => ({ ...f, admin_password: generatePassword() })); setShowPw(true); }}
              title="Generate a strong password"
            >
              <Wand2 size={14} /> Generate
            </button>
          </div>
          <div
            className="form-hint"
            style={{ color: touched && pwIssue ? 'var(--bad)' : undefined }}
          >
            {form.admin_password && !pwIssue
              ? 'Hand this to the admin securely; they can change it after signing in.'
              : 'At least 8 characters, with a letter and a number.'}
          </div>
        </div>

        <button type="submit" className="v-btn-primary" disabled={busy}>
          {busy ? 'Creating…' : 'Create organisation'}
        </button>
      </form>
    </VaultModal>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Manage
// ─────────────────────────────────────────────────────────────────────────────

function ManageOrganisationModal({ orgId, onClose, onChanged, onDeleted }) {
  const [detail, setDetail] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const [renaming, setRenaming] = useState(false);
  const [newName, setNewName] = useState('');
  const [busy, setBusy] = useState('');

  const [confirmRotate, setConfirmRotate] = useState(false);
  const [issuedKey, setIssuedKey] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(false);

  // Reload after a change. The first load is in the effect below instead,
  // written out with a cancellation flag: closing the dialog mid-request
  // must not write into a component that is already gone.
  const load = useCallback(() => superAdminApi.getTenantDetails(orgId).then(
    (d) => { setDetail(d); setLoadError(''); },
    (err) => setLoadError(err.message || 'Could not load this organisation.'),
  ), [orgId]);

  useEffect(() => {
    let cancelled = false;
    superAdminApi.getTenantDetails(orgId).then(
      (d) => { if (!cancelled) setDetail(d); },
      (err) => { if (!cancelled) setLoadError(err.message || 'Could not load this organisation.'); },
    );
    return () => { cancelled = true; };
  }, [orgId]);

  const rename = async (e) => {
    e.preventDefault();
    const name = newName.trim();
    if (!name || name === detail.name) { setRenaming(false); return; }
    setBusy('rename');
    setError('');
    try {
      const res = await superAdminApi.renameTenant(orgId, name);
      setDetail((d) => ({ ...d, name: res.tenant.name }));
      // Keep the sidebar's "working in" label honest if this is the one in use.
      if (String(getActingTenantId()) === String(orgId)) {
        setActingTenant({ id: orgId, name: res.tenant.name });
      }
      setRenaming(false);
      setNotice('Renamed.');
      onChanged();
    } catch (err) {
      setError(err.message || 'Could not rename.');
    } finally {
      setBusy('');
    }
  };

  const rotate = async () => {
    setBusy('rotate');
    setError('');
    try {
      const res = await superAdminApi.resetTenantApiKey(orgId);
      setIssuedKey(res.new_api_key);
      setDetail((d) => ({ ...d, api_key_hint: res.api_key_hint }));
      setConfirmRotate(false);
      onChanged();
    } catch (err) {
      setError(err.message || 'Could not issue a new key.');
    } finally {
      setBusy('');
    }
  };

  const remove = async () => {
    setBusy('delete');
    setError('');
    try {
      await superAdminApi.deleteTenant(orgId);
      if (String(getActingTenantId()) === String(orgId)) clearActingTenant();
      onDeleted(detail.name);
    } catch (err) {
      // Most likely something was added between opening the dialog and
      // pressing delete. Reload so the blockers shown are current.
      setError(err.message || 'Could not delete.');
      setConfirmDelete(false);
      load();
    } finally {
      setBusy('');
    }
  };

  if (loadError) {
    return (
      <VaultModal title="Organisation" onClose={onClose}>
        <div className="v-banner bad" role="alert" style={{ marginTop: '.6rem' }}>
          <AlertCircle size={14} /><span>{loadError}</span>
        </div>
      </VaultModal>
    );
  }

  if (!detail) {
    return (
      <VaultModal title="Organisation" onClose={onClose}>
        <p style={{ fontSize: '.85rem', color: 'var(--text3)', padding: '1.5rem 0', textAlign: 'center' }}>
          Loading…
        </p>
      </VaultModal>
    );
  }

  const s = detail.stats || {};
  const section = { marginTop: '1.2rem', paddingTop: '1rem', borderTop: '1px solid var(--border)' };
  const sectionHead = {
    fontSize: '.68rem', fontFamily: 'var(--mono)', textTransform: 'uppercase',
    letterSpacing: '.06em', color: 'var(--text3)', marginBottom: '.55rem',
  };

  return (
    <VaultModal title={detail.name} onClose={onClose}>
      <div style={{ fontSize: '.74rem', color: 'var(--text3)', fontFamily: 'var(--mono)' }}>
        #{detail.id} · created {shortDate(detail.created_at)}
      </div>

      {error && (
        <div className="v-banner bad" role="alert" style={{ marginTop: '.8rem' }}>
          <AlertCircle size={14} /><span>{error}</span>
        </div>
      )}
      {notice && !error && (
        <div className="v-banner ok" style={{ marginTop: '.8rem' }}>
          <Check size={14} /><span>{notice}</span>
        </div>
      )}

      {/* Name */}
      <div style={section}>
        <div style={sectionHead}>Name</div>
        {renaming ? (
          <form onSubmit={rename} style={{ display: 'flex', gap: '.4rem' }}>
            <input
              className="form-input"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              autoFocus
              maxLength={120}
              style={{ flex: 1 }}
              aria-label="New organisation name"
            />
            <button type="submit" className="v-btn" disabled={busy === 'rename'}>
              {busy === 'rename' ? 'Saving…' : 'Save'}
            </button>
            <button type="button" className="v-btn" onClick={() => setRenaming(false)}>Cancel</button>
          </form>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem' }}>
            <span style={{ flex: 1, color: 'var(--text)' }}>{detail.name}</span>
            <button
              type="button"
              className="v-btn"
              onClick={() => { setNewName(detail.name); setRenaming(true); setNotice(''); }}
            >
              <Pencil size={13} /> Rename
            </button>
          </div>
        )}
      </div>

      {/* People */}
      <div style={section}>
        <div style={sectionHead}>People</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '.35rem', marginBottom: '.7rem' }}>
          <span className="v-chip">{s.employees || 0} employees</span>
          <span className="v-chip">{s.org_admins || 0} org admins</span>
          <span className="v-chip">{s.tenant_admins || 0} tenant admins</span>
          <span className="v-chip">{s.departments || 0} departments</span>
          <span className="v-chip">{s.devices_online || 0}/{s.devices || 0} devices online</span>
        </div>
        {detail.admins?.length ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '.3rem' }}>
            {detail.admins.map((a) => (
              <div
                key={a.id}
                style={{
                  display: 'flex', alignItems: 'center', gap: '.5rem', fontSize: '.83rem',
                  padding: '.4rem .55rem', background: 'var(--bg3)', borderRadius: 8,
                  opacity: a.is_active ? 1 : 0.55,
                }}
              >
                <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  <span style={{ color: 'var(--text)' }}>{a.name}</span>
                  {a.email && <span style={{ color: 'var(--text3)' }}> · {a.email}</span>}
                </span>
                <span className={`v-chip ${a.role === 'tenant_admin' ? 'info' : ''}`}>
                  {a.role === 'tenant_admin' ? 'Tenant Admin' : 'Org Admin'}
                </span>
                {!a.is_active && <span className="v-chip">inactive</span>}
              </div>
            ))}
          </div>
        ) : (
          <div className="v-banner warn" style={{ marginBottom: 0 }}>
            <AlertTriangle size={14} />
            <span>No admins. Nobody can sign in to administer this organisation.</span>
          </div>
        )}
      </div>

      {/* Office hours */}
      {detail.settings && (
        <div style={section}>
          <div style={sectionHead}>Office hours</div>
          <div style={{ fontSize: '.83rem', color: 'var(--text2)', lineHeight: 1.7 }}>
            {hhmm(detail.settings.office_start_time)}–{hhmm(detail.settings.office_end_time)},{' '}
            {workingDays(detail.settings.working_days)}
            <br />
            {detail.settings.late_threshold_minutes} min grace ·{' '}
            {detail.settings.min_working_hours} h minimum day
          </div>
        </div>
      )}

      {/* API key */}
      <div style={section}>
        <div style={sectionHead}>API key</div>
        {issuedKey ? (
          <RevealOnce
            label="New API key"
            value={issuedKey}
            note="Copy this now — it is not shown again. The previous key has already stopped working."
          />
        ) : confirmRotate ? (
          <>
            <div className="v-banner warn">
              <AlertTriangle size={14} />
              <span>
                The current key stops working the moment a new one is issued. Every fingerprint
                reader and integration using it will fail until it is updated.
              </span>
            </div>
            <div style={{ display: 'flex', gap: '.4rem' }}>
              <button type="button" className="v-btn" onClick={() => setConfirmRotate(false)}>Cancel</button>
              <button
                type="button"
                className="v-btn danger"
                onClick={rotate}
                disabled={busy === 'rotate'}
                style={{ color: 'var(--warn)' }}
              >
                <RefreshCw size={13} /> {busy === 'rotate' ? 'Issuing…' : 'Issue new key'}
              </button>
            </div>
          </>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem' }}>
            <span style={{ flex: 1, fontFamily: 'var(--mono)', fontSize: '.85rem', color: 'var(--text2)' }}>
              {detail.api_key_hint || '—'}
            </span>
            <button type="button" className="v-btn" onClick={() => { setConfirmRotate(true); setNotice(''); }}>
              <RefreshCw size={13} /> Issue new key
            </button>
          </div>
        )}
      </div>

      {/* Delete */}
      <div style={section}>
        <div style={sectionHead}>Delete</div>
        {detail.can_delete ? (
          confirmDelete ? (
            <>
              <div className="v-banner bad">
                <AlertTriangle size={14} />
                <span>
                  This removes <strong>{detail.name}</strong>, its departments, settings and
                  Tenant Admin accounts. It can&apos;t be undone.
                </span>
              </div>
              <div style={{ display: 'flex', gap: '.4rem' }}>
                <button type="button" className="v-btn" onClick={() => setConfirmDelete(false)}>Cancel</button>
                <button
                  type="button"
                  className="btn btn-red"
                  onClick={remove}
                  disabled={busy === 'delete'}
                >
                  <Trash2 size={13} style={{ marginRight: 6 }} />
                  {busy === 'delete' ? 'Deleting…' : `Delete ${detail.name}`}
                </button>
              </div>
            </>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem' }}>
              <span style={{ flex: 1, fontSize: '.82rem', color: 'var(--text3)' }}>
                Empty — nobody has added people, devices or records yet.
              </span>
              <button
                type="button"
                className="v-btn danger"
                onClick={() => { setConfirmDelete(true); setNotice(''); }}
              >
                <Trash2 size={13} /> Delete
              </button>
            </div>
          )
        ) : (
          <div style={{ fontSize: '.82rem', color: 'var(--text3)', lineHeight: 1.55 }}>
            Only an empty organisation can be deleted. This one still holds:
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '.35rem', marginTop: '.5rem' }}>
              {detail.delete_blockers.map((b) => (
                <span key={b.table} className="v-chip">{b.count} {b.label}</span>
              ))}
            </div>
          </div>
        )}
      </div>
    </VaultModal>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────────────────────

export default function Organisations() {
  const navigate = useNavigate();

  const [overview, setOverview] = useState(null);
  const [orgs, setOrgs] = useState(null);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const [creating, setCreating] = useState(false);
  const [managing, setManaging] = useState(null);
  const [toast, setToast] = useState('');

  const actingId = getActingTenantId();

  const fetchAll = () => Promise.all([superAdminApi.getOverview(), superAdminApi.getTenants()]);

  // Reload after a change or on Refresh. The first load is in the effect
  // below, with a cancellation flag, like the modal's.
  const load = useCallback(() => fetchAll()
    .then(
      ([ov, list]) => { setOverview(ov); setOrgs(list); setError(''); },
      (err) => setError(err.message || 'Could not load organisations.'),
    )
    .finally(() => setRefreshing(false)), []);

  useEffect(() => {
    let cancelled = false;
    fetchAll().then(
      ([ov, list]) => { if (!cancelled) { setOverview(ov); setOrgs(list); } },
      (err) => { if (!cancelled) setError(err.message || 'Could not load organisations.'); },
    );
    return () => { cancelled = true; };
  }, []);

  const refresh = () => {
    setRefreshing(true);
    load();
  };

  useEffect(() => {
    if (!toast) return undefined;
    const t = setTimeout(() => setToast(''), 3500);
    return () => clearTimeout(t);
  }, [toast]);

  const workIn = (org) => {
    setActingTenant({ id: org.id, name: org.name });
    navigate('/super/dashboard');
  };

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return (orgs || []).filter((o) => !q || o.name.toLowerCase().includes(q) || String(o.id) === q);
  }, [orgs, filter]);

  const people = overview
    ? (overview.employees || 0) + (overview.org_admins || 0) + (overview.tenant_admins || 0)
    : null;

  return (
    <DashboardLayout title="Organisations" role="superadmin" label="Super Admin" abbr="SA">
      {toast && (
        <div
          role="status"
          style={{
            position: 'fixed', bottom: 24, right: 24, zIndex: 1000,
            background: 'rgba(34,197,94,0.95)', color: 'white',
            padding: '12px 20px', borderRadius: 8,
          }}
        >
          {toast}
        </div>
      )}

      <div className="stats-grid" style={{ marginBottom: '1.5rem' }}>
        <Stat tone="purple" label="Organisations" value={overview?.organisations} sub="On this platform" />
        <Stat
          tone="teal"
          label="People"
          value={people}
          sub={overview ? `${overview.employees} employees · ${overview.org_admins + overview.tenant_admins} admins` : null}
        />
        <Stat
          tone="green"
          label="Devices online"
          value={overview ? `${overview.devices_online}/${overview.devices}` : null}
          sub="Fingerprint readers"
        />
        <Stat tone="blue" label="Attendance today" value={overview?.attendance_today} sub="Punches since midnight" />
      </div>

      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: '1.25rem', flexWrap: 'wrap', gap: '.75rem',
      }}
      >
        <div style={{ display: 'flex', gap: '.5rem', flex: 1, maxWidth: 360, minWidth: 220 }}>
          <div style={{ flex: 1, position: 'relative' }}>
            <Search
              size={16}
              style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text3)' }}
            />
            <input
              className="form-input"
              placeholder="Search by name or #id"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              style={{ paddingLeft: 32, width: '100%' }}
              aria-label="Search organisations"
            />
          </div>
          <button type="button" className="btn btn-ghost" onClick={refresh} title="Refresh" aria-label="Refresh">
            <RefreshCw size={16} className={refreshing ? 'spin' : ''} />
          </button>
        </div>
        <button type="button" className="btn btn-teal" onClick={() => setCreating(true)}>
          <Plus size={16} style={{ marginRight: 6 }} /> New organisation
        </button>
      </div>

      {error && (
        <div className="v-banner bad" role="alert">
          <AlertCircle size={14} /><span>{error}</span>
        </div>
      )}

      {orgs === null && !error && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '1rem' }}>
          {[1, 2, 3].map((i) => (
            <div key={i} className="card-box" style={{ height: 190, opacity: 0.5 }} />
          ))}
        </div>
      )}

      {orgs !== null && orgs.length === 0 && (
        <div className="card-box v-empty">
          <div className="v-empty-icon"><Building2 size={22} /></div>
          <div className="v-empty-title">No organisations yet</div>
          <div className="v-empty-body">
            Create the first one — it comes with a department, office hours and a Tenant Admin
            who can sign in straight away.
          </div>
          <button type="button" className="btn btn-teal" style={{ marginTop: '1rem' }} onClick={() => setCreating(true)}>
            <Plus size={16} style={{ marginRight: 6 }} /> New organisation
          </button>
        </div>
      )}

      {orgs !== null && orgs.length > 0 && visible.length === 0 && (
        <p style={{ color: 'var(--text3)', fontSize: '.88rem', textAlign: 'center', padding: '2rem 0' }}>
          Nothing matches “{filter}”.
        </p>
      )}

      {visible.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(320px, 100%), 1fr))', gap: '1rem' }}>
          {visible.map((org) => (
            <OrgCard
              key={org.id}
              org={org}
              active={String(org.id) === String(actingId)}
              onWorkIn={workIn}
              onManage={(o) => setManaging(o.id)}
            />
          ))}
        </div>
      )}

      {creating && (
        <CreateOrganisationModal
          onClose={() => setCreating(false)}
          onCreated={load}
          onWorkIn={(tenant) => { setCreating(false); workIn(tenant); }}
        />
      )}

      {managing !== null && (
        <ManageOrganisationModal
          orgId={managing}
          onClose={() => setManaging(null)}
          onChanged={load}
          onDeleted={(name) => { setManaging(null); setToast(`“${name}” was deleted.`); load(); }}
        />
      )}

      <style>{`
        .spin { animation: org-spin 0.8s linear infinite; }
        @keyframes org-spin { to { transform: rotate(360deg); } }
      `}</style>
    </DashboardLayout>
  );
}
