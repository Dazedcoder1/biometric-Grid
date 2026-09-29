// src/pages/vault/Credentials.jsx
//
// The credential vault. Racks down the side, credentials in the middle,
// reveal behind a step-up prompt.
//
// Two rules this screen keeps:
//   1. A revealed secret lives in component state only. Never localStorage,
//      never a URL, never a global. Navigating away loses it, which is the
//      point.
//   2. Revealed secrets auto-hide after 30 seconds. A walked-away laptop
//      should not leave a password on screen indefinitely.

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertCircle, CheckCircle, Copy, Eye, EyeOff, KeyRound, Plus,
  RefreshCw, Search, Share2, Shield, Trash2, Users, X,
} from 'lucide-react';

import DashboardLayout from '../../layouts/DashboardLayout';
import ConfirmationModal from '../../components/ConfirmationModal';
import VaultModal from '../../components/VaultModal';
import { useAuth } from '../../context/AuthContext';
import usePermissions from '../../hooks/usePermissions';
import { vaultApi } from '../../services/api';
import { DEFAULTS, estimateStrength, generatePassword } from '../../utils/passwordGenerator';
import { sidebarPropsFor } from '../../utils/sidebarRole';
import {
  KINDS, expiryStatus, isSharedWithMe, kindMeta, relativeAge,
} from '../../utils/credentialMeta';
import './vault.css';

const REVEAL_SECONDS = 30;

// Racks are filtered in the browser so switching between them is instant and
// the counts beside each name are exact. That only holds while the whole list
// is in hand, so ask for the server's maximum and say so plainly if we hit it,
// rather than showing counts that quietly describe the first page only.
const LIST_LIMIT = 500;

const SEARCH_DEBOUNCE_MS = 250;

export default function Credentials() {
  const { user } = useAuth();
  // Offering an action the server will refuse is how "This action requires the
  // 'x' permission" reaches people. An Employee holds no credential.delete, so
  // the delete button was a 403 with extra steps.
  const { can } = usePermissions();
  const [vaults, setVaults] = useState([]);
  const [activeRack, setActiveRack] = useState(null);
  const [items, setItems] = useState([]);

  // Two states, not one: `typed` updates on every keystroke so the field stays
  // responsive, `search` lags behind it and is what actually hits the API.
  // Previously every character fired a request, and out-of-order responses
  // could leave the list showing results for a prefix of what was typed.
  const [typed, setTyped] = useState('');
  const [search, setSearch] = useState('');

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [flash, setFlash] = useState('');

  // id -> { secret, notes, expiresIn }
  const [revealed, setRevealed] = useState({});
  const [pendingReveal, setPendingReveal] = useState(null);
  const [code, setCode] = useState('');
  const [stepUpBusy, setStepUpBusy] = useState(false);

  const [showCreate, setShowCreate] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [mfaEnrolled, setMfaEnrolled] = useState(null);

  // Held in a ref, not state: it must not survive a reload, and it should not
  // trigger a re-render when it changes.
  const stepUpToken = useRef(null);
  const stepUpExpiry = useRef(0);

  const note = (msg) => { setFlash(msg); setTimeout(() => setFlash(''), 3500); };

  // ─── load ──────────────────────────────────────────────────────────────────

  const loadVaults = useCallback(async () => {
    const data = await vaultApi.vaults();
    setVaults(data);
  }, []);

  const loadItems = useCallback(async () => {
    const data = await vaultApi.list({
      search: search || undefined,
      limit: LIST_LIMIT,
    });
    setItems(data);
  }, [search]);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        await loadVaults();
        const status = await vaultApi.mfaStatus();
        setMfaEnrolled(status.enrolled);
      } catch (err) {
        setError(err.message || 'Could not load your vault.');
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const t = setTimeout(() => setSearch(typed.trim()), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [typed]);

  useEffect(() => {
    loadItems().catch((err) => setError(err.message));
  }, [loadItems]);

  // ─── auto-hide revealed secrets ────────────────────────────────────────────

  useEffect(() => {
    if (Object.keys(revealed).length === 0) return undefined;
    const timer = setInterval(() => {
      setRevealed((prev) => {
        const next = {};
        for (const [id, entry] of Object.entries(prev)) {
          if (entry.expiresIn > 1) next[id] = { ...entry, expiresIn: entry.expiresIn - 1 };
        }
        return next;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [revealed]);

  // ─── reveal ────────────────────────────────────────────────────────────────

  const tokenIsFresh = () => stepUpToken.current && Date.now() < stepUpExpiry.current;

  const doReveal = async (id, token) => {
    const data = await vaultApi.reveal(id, token);
    setRevealed((prev) => ({
      ...prev,
      [id]: { secret: data.secret, notes: data.notes, expiresIn: REVEAL_SECONDS },
    }));
  };

  const handleReveal = async (item) => {
    if (revealed[item.id]) {
      setRevealed((prev) => {
        const next = { ...prev };
        delete next[item.id];
        return next;
      });
      return;
    }

    setError('');
    // Reuse a live assertion so several reveals in one sitting do not each
    // demand a fresh code.
    if (tokenIsFresh()) {
      try {
        await doReveal(item.id, stepUpToken.current);
        return;
      } catch (err) {
        if (!err.stepUpRequired) { setError(err.message); return; }
        stepUpToken.current = null;   // expired or revoked server-side
      }
    }
    setPendingReveal(item);
  };

  const submitStepUp = async (e) => {
    e.preventDefault();
    setStepUpBusy(true);
    setError('');
    try {
      const res = await vaultApi.stepUp(code.trim());
      stepUpToken.current = res.step_up_token;
      // Trust the server's expiry, minus a second of slack for clock skew.
      stepUpExpiry.current = new Date(res.expires_at).getTime() - 1000;
      await doReveal(pendingReveal.id, res.step_up_token);
      setPendingReveal(null);
      setCode('');
    } catch (err) {
      setError(err.message || 'That code was not accepted.');
    } finally {
      setStepUpBusy(false);
    }
  };

  const handleCopy = async (item) => {
    const entry = revealed[item.id];
    if (!entry) return;
    try {
      await navigator.clipboard.writeText(entry.secret);
      note('Copied. This was recorded in the audit log.');
      vaultApi.recordCopy(item.id).catch(() => {});
    } catch {
      setError('Could not reach the clipboard. Select the value and copy it manually.');
    }
  };

  const handleDelete = async () => {
    try {
      await vaultApi.remove(deleteTarget.id);
      setDeleteTarget(null);
      note('Credential deleted.');
      await loadItems();
    } catch (err) {
      setError(err.message);
    }
  };

  // ─── derived ───────────────────────────────────────────────────────────────

  const racks = useMemo(
    () => vaults.find((v) => v.kind === 'personal')?.racks || [],
    [vaults],
  );

  const truncated = items.length >= LIST_LIMIT;

  const countByRack = useMemo(() => {
    const counts = {};
    for (const it of items) counts[it.rack_id] = (counts[it.rack_id] || 0) + 1;
    return counts;
  }, [items]);

  const visible = useMemo(
    () => (activeRack === null ? items : items.filter((i) => i.rack_id === activeRack)),
    [items, activeRack],
  );

  // ─── render ────────────────────────────────────────────────────────────────

  return (
    <DashboardLayout title="Credential Vault" {...sidebarPropsFor(user)}>
      {flash && (
        <div className="v-banner ok">
          <CheckCircle size={14} />
          <span>{flash}</span>
        </div>
      )}
      {error && (
        <div className="v-banner bad">
          <AlertCircle size={14} />
          <span>{error}</span>
        </div>
      )}
      {truncated && (
        <div className="v-banner warn">
          <AlertCircle size={14} />
          <span>
            Showing the first {LIST_LIMIT} credentials. Search to narrow it down —
            the counts beside each rack cover only what is listed here.
          </span>
        </div>
      )}

      {mfaEnrolled === false && <MfaPrompt onDone={() => setMfaEnrolled(true)} />}

      <div className="v-wrap">
        <aside>
          <div className="v-racks-label">Racks</div>
          <div className="v-racks">
            {/* Always reachable, so a credential can never be invisible just
                because it sits in a rack that is not selected. */}
            <button
              type="button"
              className={`v-rack ${activeRack === null ? 'active' : ''}`}
              onClick={() => setActiveRack(null)}
            >
              All credentials
              <span className="v-rack-count">{items.length}</span>
            </button>
            {racks.map((r) => (
              <button
                type="button"
                key={r.id}
                className={`v-rack ${activeRack === r.id ? 'active' : ''}`}
                onClick={() => setActiveRack(r.id)}
              >
                {r.name}
                <span className="v-rack-count">{countByRack[r.id] || 0}</span>
              </button>
            ))}
          </div>
        </aside>

        <main>
          <div style={{ display: 'flex', gap: '.6rem', marginBottom: '1rem' }}>
            <div style={{ position: 'relative', flex: 1 }}>
              <Search
                size={14}
                style={{ position: 'absolute', left: 11, top: '50%',
                  transform: 'translateY(-50%)', color: 'var(--text3)' }}
              />
              <input
                className="form-input"
                placeholder="Search name, username or URL"
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                style={{ paddingLeft: 32, width: '100%' }}
              />
              {typed && (
                <button
                  type="button"
                  onClick={() => setTyped('')}
                  aria-label="Clear search"
                  style={{ position: 'absolute', right: 8, top: '50%',
                    transform: 'translateY(-50%)', background: 'none',
                    border: 'none', color: 'var(--text3)', cursor: 'pointer',
                    display: 'flex', padding: 4 }}
                >
                  <X size={13} />
                </button>
              )}
            </div>
            <button type="button" className="v-btn" onClick={() => setShowCreate(true)}>
              <Plus size={14} /> New
            </button>
          </div>

          <div className="card-box" style={{ padding: 0, overflow: 'hidden' }}>
            {loading ? (
              <div className="v-empty">
                <div className="v-empty-body">Loading…</div>
              </div>
            ) : visible.length === 0 ? (
              <EmptyState
                searching={!!search}
                rackSelected={activeRack !== null}
                onCreate={() => setShowCreate(true)}
                onShowAll={() => { setActiveRack(null); setTyped(''); }}
              />
            ) : (
              visible.map((item) => (
                <CredentialRow
                  key={item.id}
                  item={item}
                  user={user}
                  entry={revealed[item.id]}
                  canReveal={can('credential.reveal')}
                  canDelete={can('credential.delete')}
                  canShare={can('share.view')}
                  onReveal={() => handleReveal(item)}
                  onCopy={() => handleCopy(item)}
                  onDelete={() => setDeleteTarget(item)}
                />
              ))
            )}
          </div>
        </main>
      </div>

      {pendingReveal && (
        <VaultModal
          title="Confirm it's you"
          onClose={() => { setPendingReveal(null); setCode(''); }}
        >
          <form onSubmit={submitStepUp}>
            <p style={{ fontSize: '.84rem', color: 'var(--text2)', marginTop: '.4rem' }}>
              Revealing <strong style={{ color: 'var(--text)' }}>{pendingReveal.name}</strong>{' '}
              needs a code from your authenticator. This is recorded in the audit log.
            </p>
            <input
              className="form-input"
              autoFocus
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              placeholder="000000"
              aria-label="Six-digit authentication code"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
              style={{ width: '100%', fontFamily: 'var(--mono)', fontSize: '1.4rem',
                letterSpacing: '.3em', textAlign: 'center', padding: '.7rem' }}
            />
            <button type="submit" className="v-btn-primary"
              disabled={code.length < 6 || stepUpBusy}>
              {stepUpBusy ? 'Checking…' : 'Reveal'}
            </button>
          </form>
        </VaultModal>
      )}

      {showCreate && (
        <CreateModal
          racks={racks}
          defaultRack={activeRack}
          onClose={() => setShowCreate(false)}
          onCreated={async (created) => {
            setShowCreate(false);
            note('Credential saved.');
            // Jump to the rack it landed in. Saving into a rack other than the
            // one on screen previously looked like the save had failed.
            if (created?.rack_id && created.rack_id !== activeRack) {
              setActiveRack(created.rack_id);
            }
            await loadItems();
          }}
          onError={setError}
        />
      )}

      <ConfirmationModal
        isOpen={!!deleteTarget}
        title="Delete credential"
        message={`Delete "${deleteTarget?.name}"? Its history stays in the audit log.`}
        confirmText="Delete"
        type="danger"
        onConfirm={handleDelete}
        onClose={() => setDeleteTarget(null)}
      />
    </DashboardLayout>
  );
}

// ─── one row ─────────────────────────────────────────────────────────────────

function CredentialRow({
  item, user, entry, canReveal, canDelete, canShare, onReveal, onCopy, onDelete,
}) {
  const { icon: KindIcon, label: kindLabel } = kindMeta(item.kind);
  const expiry = expiryStatus(item.expires_at);
  const shared = isSharedWithMe(item, user);
  const lastUsed = relativeAge(item.last_accessed_at);

  return (
    <div className="v-row">
      <div className="v-kind" title={kindLabel} aria-hidden="true">
        <KindIcon size={16} strokeWidth={1.75} />
      </div>

      <div className="v-row-main">
        <div className="v-row-name">
          {item.name}
          {item.has_2fa && (
            <Shield size={12} style={{ color: 'var(--text3)' }}
              aria-label="This account has 2FA enabled" />
          )}
        </div>

        <div className="v-row-sub">
          {item.username || 'No username'}
          {item.url ? ` · ${item.url}` : ''}
        </div>

        {/* Facts, not decoration. Each chip is a field the list endpoint
            already returns; nothing here is inferred. */}
        <div className="v-chips">
          <span className="v-chip">{kindLabel}</span>
          {shared && (
            <span className="v-chip info"><Users size={9} /> Shared with you</span>
          )}
          {expiry && (
            <span className={`v-chip ${expiry.tone || ''}`}>{expiry.label}</span>
          )}
          <span className="v-chip">
            {lastUsed ? `used ${lastUsed} ago` : 'never used'}
          </span>
        </div>

        {entry && (
          <div style={{ marginTop: '.6rem', maxWidth: 420 }}>
            <span className="v-secret">{entry.secret}</span>
            <div className="v-countdown">
              <div
                className="v-countdown-fill"
                style={{ width: `${(entry.expiresIn / 30) * 100}%` }}
              />
            </div>
            <div style={{ fontSize: '.7rem', color: 'var(--text3)', marginTop: '.25rem' }}>
              Hides in {entry.expiresIn}s
            </div>
            {entry.notes && (
              <div style={{ fontSize: '.76rem', color: 'var(--text2)', marginTop: '.4rem',
                whiteSpace: 'pre-wrap' }}>
                {entry.notes}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="v-row-actions">
        {canReveal && (
          <button type="button" className="v-btn" onClick={onReveal}>
            {entry ? <EyeOff size={13} /> : <Eye size={13} />}
            {entry ? 'Hide' : 'Reveal'}
          </button>
        )}
        {entry && (
          <button type="button" className="v-btn" onClick={onCopy}>
            <Copy size={13} /> Copy
          </button>
        )}
        {/* Link, not <a href>: an anchor reloads the whole app, which throws
            away every revealed secret on screen and re-runs auth. */}
        {canShare && (
          <Link className="v-btn" to={`/vault/credential/${item.id}`}
            title="Sharing and activity" aria-label="Sharing and activity">
            <Share2 size={13} />
          </Link>
        )}
        {canDelete && (
          <button type="button" className="v-btn danger" onClick={onDelete}
            title="Delete" aria-label="Delete credential">
            <Trash2 size={13} />
          </button>
        )}
      </div>
    </div>
  );
}

// ─── empty state ─────────────────────────────────────────────────────────────

// Three different nothings, because the way out of each differs. "Nothing here
// yet" under an active search is misleading — there may be plenty here, just
// not matching.
function EmptyState({ searching, rackSelected, onCreate, onShowAll }) {
  if (searching) {
    return (
      <div className="v-empty">
        <div className="v-empty-icon"><Search size={22} strokeWidth={1.5} /></div>
        <div className="v-empty-title">No matches</div>
        <p className="v-empty-body">
          Nothing matches that search in {rackSelected ? 'this rack' : 'your vault'}.
        </p>
        <button type="button" className="v-btn" style={{ marginTop: '.8rem' }}
          onClick={onShowAll}>
          Clear search
        </button>
      </div>
    );
  }

  if (rackSelected) {
    return (
      <div className="v-empty">
        <div className="v-empty-icon"><KeyRound size={22} strokeWidth={1.5} /></div>
        <div className="v-empty-title">This rack is empty</div>
        <p className="v-empty-body">
          Credentials you add here stay encrypted at rest and are only decrypted
          when you reveal them.
        </p>
        <div style={{ display: 'flex', gap: '.5rem', justifyContent: 'center',
          marginTop: '.8rem' }}>
          <button type="button" className="v-btn" onClick={onShowAll}>
            Show all credentials
          </button>
          <button type="button" className="v-btn" onClick={onCreate}>
            <Plus size={13} /> Add one
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="v-empty">
      <div className="v-empty-icon"><KeyRound size={22} strokeWidth={1.5} /></div>
      <div className="v-empty-title">Your vault is empty</div>
      <p className="v-empty-body">
        Add a password, API key or certificate. It is encrypted before it is
        stored, and every reveal is recorded in the audit log.
      </p>
      <button type="button" className="v-btn" style={{ marginTop: '.8rem' }}
        onClick={onCreate}>
        <Plus size={13} /> Add your first credential
      </button>
    </div>
  );
}

// ─── MFA enrolment ───────────────────────────────────────────────────────────

function MfaPrompt({ onDone }) {
  const [enrolment, setEnrolment] = useState(null);   // { secret, provisioning_uri }
  const [code, setCode] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const canvasRef = useRef(null);

  const start = async () => {
    setErr('');
    try {
      setEnrolment(await vaultApi.beginEnrolment());
    } catch (e) {
      setErr(e.message);
    }
  };

  // Render the QR locally. The otpauth:// URI contains the TOTP secret, so it
  // must never go to an external QR service — that would hand the second
  // factor to a third party. `qrcode` draws it in this browser and nothing
  // leaves the page.
  useEffect(() => {
    if (!enrolment?.provisioning_uri || !canvasRef.current) return undefined;
    let cancelled = false;

    import('qrcode')
      .then((QR) => {
        if (cancelled) return;
        QR.toCanvas(canvasRef.current, enrolment.provisioning_uri, {
          width: 180, margin: 1,
        }).catch(() => setErr('Could not draw the QR code — use the key below.'));
      })
      .catch(() => {
        // Library missing: the manual key below still works, so say so rather
        // than leaving a blank square.
        setErr('QR rendering unavailable — enter the key manually instead.');
      });

    return () => { cancelled = true; };
  }, [enrolment]);

  const confirm = async (e) => {
    e.preventDefault();
    setBusy(true);
    setErr('');
    try {
      await vaultApi.confirmEnrolment(code);
      onDone();
    } catch (e2) {
      setErr(e2.message);
      setCode('');
    } finally {
      setBusy(false);
    }
  };

  // Grouped in fours. A 32-character base32 string typed off a screen in one
  // run is a transcription error waiting to happen.
  const grouped = enrolment?.secret
    ? enrolment.secret.match(/.{1,4}/g).join(' ')
    : '';

  return (
    <div className="card-box" style={{ marginBottom: '1.25rem',
      borderLeft: '3px solid var(--amber)' }}>
      <h4 style={{ margin: '0 0 .4rem', fontSize: '.95rem' }}>
        Set up your authenticator
      </h4>
      <p style={{ fontSize: '.84rem', color: 'var(--text2)', marginTop: 0 }}>
        Revealing a secret needs a second factor. Enrol once, and you will only
        be asked for a code when you actually reveal something.
      </p>
      {err && (
        <div style={{ fontSize: '.8rem', color: '#f87171', marginBottom: '.5rem' }}>
          {err}
        </div>
      )}

      {!enrolment ? (
        <button type="button" className="v-btn" onClick={start}>Start setup</button>
      ) : (
        <div style={{ display: 'flex', gap: '1.25rem', flexWrap: 'wrap',
          alignItems: 'flex-start' }}>
          {/* White plate on purpose: a QR needs light quiet zones to scan, and
              in dark mode the card background is not light enough. */}
          <div style={{ background: '#fff', padding: 8, borderRadius: 8 }}>
            <canvas ref={canvasRef} />
          </div>

          <div style={{ flex: 1, minWidth: 240 }}>
            <p style={{ fontSize: '.8rem', color: 'var(--text2)', marginTop: 0 }}>
              Scan this with Google Authenticator, 1Password, Authy or similar.
            </p>

            <div style={{ fontSize: '.72rem', color: 'var(--text3)', marginBottom: '.2rem' }}>
              Or enter this key by hand:
            </div>
            <div style={{ display: 'flex', gap: '.4rem', alignItems: 'center',
              marginBottom: '.8rem' }}>
              <code className="v-secret" style={{ fontSize: '.78rem' }}>
                {grouped}
              </code>
              <button type="button" className="v-btn" aria-label="Copy setup key"
                onClick={() => navigator.clipboard.writeText(enrolment.secret)}>
                <Copy size={12} />
              </button>
            </div>

            <form onSubmit={confirm}>
              <div style={{ fontSize: '.72rem', color: 'var(--text3)', marginBottom: '.25rem' }}>
                Then enter the 6-digit code it shows:
              </div>
              <div style={{ display: 'flex', gap: '.5rem' }}>
                <input
                  className="form-input"
                  autoFocus
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  placeholder="000000"
                  aria-label="Six-digit code from your authenticator"
                  maxLength={6}
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                  style={{ fontFamily: 'var(--mono)', width: 120,
                    letterSpacing: '.15em' }}
                />
                <button className="v-btn" type="submit"
                  disabled={code.length < 6 || busy}>
                  {busy ? 'Checking…' : 'Confirm'}
                </button>
              </div>
            </form>

            <div style={{ fontSize: '.7rem', color: 'var(--text3)', marginTop: '.6rem' }}>
              This key is shown once. If you lose it, start setup again.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── create ──────────────────────────────────────────────────────────────────

function CreateModal({ racks, defaultRack, onClose, onCreated, onError }) {
  const [form, setForm] = useState({
    rack_id: defaultRack || racks[0]?.id, name: '', username: '', url: '',
    secret: '', notes: '', kind: 'password', has_2fa: false,
  });
  const [opts, setOpts] = useState(DEFAULTS);
  const [busy, setBusy] = useState(false);
  const [showSecret, setShowSecret] = useState(false);

  const strength = estimateStrength(form.secret);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const regenerate = () => {
    try {
      set('secret', generatePassword(opts));
      // A generated value nobody can read is a value nobody checks. Typed
      // secrets stay masked; generated ones are shown until dismissed.
      setShowSecret(true);
    } catch (e) {
      onError(e.message);
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const created = await vaultApi.create(form);
      await onCreated(created);
    } catch (err) {
      onError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const toneColour = { danger: '#ef4444', warning: '#f59e0b',
    success: '#22c55e', muted: 'var(--text3)' }[strength.tone];

  return (
    <VaultModal title="New credential" onClose={onClose}>
      <form onSubmit={submit}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr',
          gap: '.7rem', marginTop: '.8rem' }}>
          <div>
            <label className="form-label" htmlFor="c-rack">Rack</label>
            <select id="c-rack" className="form-input form-select" value={form.rack_id}
              onChange={(e) => set('rack_id', Number(e.target.value))}
              style={{ width: '100%' }}>
              {racks.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </select>
          </div>
          <div>
            <label className="form-label" htmlFor="c-kind">Type</label>
            <select id="c-kind" className="form-input form-select" value={form.kind}
              onChange={(e) => set('kind', e.target.value)} style={{ width: '100%' }}>
              {KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
            </select>
          </div>
        </div>

        <label className="form-label" htmlFor="c-name"
          style={{ display: 'block', marginTop: '.7rem' }}>Name</label>
        <input id="c-name" className="form-input" required value={form.name}
          onChange={(e) => set('name', e.target.value)}
          style={{ width: '100%' }} />

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr',
          gap: '.7rem', marginTop: '.7rem' }}>
          <div>
            <label className="form-label" htmlFor="c-user">Username</label>
            <input id="c-user" className="form-input" value={form.username}
              onChange={(e) => set('username', e.target.value)}
              style={{ width: '100%' }} />
          </div>
          <div>
            <label className="form-label" htmlFor="c-url">URL</label>
            <input id="c-url" className="form-input" value={form.url}
              onChange={(e) => set('url', e.target.value)}
              style={{ width: '100%' }} />
          </div>
        </div>

        <label className="form-label" htmlFor="c-secret"
          style={{ display: 'block', marginTop: '.7rem' }}>Secret</label>
        <div style={{ display: 'flex', gap: '.4rem' }}>
          <input id="c-secret" className="form-input" required
            type={showSecret ? 'text' : 'password'}
            value={form.secret}
            onChange={(e) => set('secret', e.target.value)}
            style={{ flex: 1, fontFamily: 'var(--mono)', minWidth: 0 }} />
          <button type="button" className="v-btn"
            onClick={() => setShowSecret((s) => !s)}
            aria-label={showSecret ? 'Hide secret' : 'Show secret'}>
            {showSecret ? <EyeOff size={13} /> : <Eye size={13} />}
          </button>
          <button type="button" className="v-btn" onClick={regenerate}>
            <RefreshCw size={13} /> Generate
          </button>
        </div>

        {form.secret && (
          <div style={{ marginTop: '.5rem' }}>
            <div style={{ height: 4, background: 'var(--bg3)', borderRadius: 2 }}>
              <div style={{ height: '100%', width: `${strength.percent}%`,
                background: toneColour, borderRadius: 2, transition: 'width .2s' }} />
            </div>
            <div style={{ fontSize: '.72rem', color: 'var(--text3)', marginTop: '.3rem' }}>
              {strength.label} · ~{strength.bits} bits of entropy
            </div>
          </div>
        )}

        <div style={{ display: 'flex', gap: '.8rem', flexWrap: 'wrap',
          fontSize: '.75rem', marginTop: '.6rem', color: 'var(--text2)',
          alignItems: 'center' }}>
          <label>
            Length{' '}
            <input type="number" min={8} max={128} value={opts.length}
              onChange={(e) => setOpts({ ...opts, length: Number(e.target.value) })}
              style={{ width: 56 }} className="form-input" />
          </label>
          {['upper', 'digits', 'symbols'].map((k) => (
            <label key={k} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              <input type="checkbox" checked={opts[k]}
                onChange={(e) => setOpts({ ...opts, [k]: e.target.checked })} />
              {k}
            </label>
          ))}
        </div>

        <label className="form-label" htmlFor="c-notes"
          style={{ display: 'block', marginTop: '.7rem' }}>
          Notes (encrypted)
        </label>
        <textarea id="c-notes" className="form-input" rows={2} value={form.notes}
          onChange={(e) => set('notes', e.target.value)}
          style={{ width: '100%', fontFamily: 'inherit' }} />

        <label style={{ display: 'flex', alignItems: 'center', gap: 6,
          fontSize: '.8rem', marginTop: '.6rem', color: 'var(--text2)' }}>
          <input type="checkbox" checked={form.has_2fa}
            onChange={(e) => set('has_2fa', e.target.checked)} />
          This account has 2FA enabled
        </label>

        <button type="submit" className="v-btn-primary" disabled={busy}>
          {busy ? 'Saving…' : 'Save credential'}
        </button>
      </form>
    </VaultModal>
  );
}
