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
import {
  AlertCircle, CheckCircle, Copy, Eye, EyeOff, KeyRound, Plus,
  RefreshCw, Search, Share2, Shield, Trash2, X,
} from 'lucide-react';

import DashboardLayout from '../../layouts/DashboardLayout';
import ConfirmationModal from '../../components/ConfirmationModal';
import { useAuth } from '../../context/AuthContext';
import { vaultApi } from '../../services/api';
import { DEFAULTS, estimateStrength, generatePassword } from '../../utils/passwordGenerator';
import { sidebarPropsFor } from '../../utils/sidebarRole';

const REVEAL_SECONDS = 30;

export default function Credentials() {
  const { user } = useAuth();
  const [vaults, setVaults] = useState([]);
  const [activeRack, setActiveRack] = useState(null);
  const [items, setItems] = useState([]);
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
    const personal = data.find((v) => v.kind === 'personal');
    if (personal?.racks?.length && !activeRack) setActiveRack(personal.racks[0].id);
  }, [activeRack]);

  const loadItems = useCallback(async () => {
    // activeRack === null means "all racks", not "don't load". An early return
    // here made the list permanently empty whenever rack selection failed for
    // any reason — which is a blank screen with no error to explain it.
    const data = await vaultApi.list({
      rackId: activeRack || undefined,
      search: search || undefined,
    });
    setItems(data);
  }, [activeRack, search]);

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
    loadItems().catch((err) => setError(err.message));
  }, [activeRack, search, loadItems]);

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

  const racks = useMemo(
    () => vaults.find((v) => v.kind === 'personal')?.racks || [],
    [vaults],
  );

  // ─── render ────────────────────────────────────────────────────────────────

  return (
    <DashboardLayout title="Credential Vault" {...sidebarPropsFor(user)}>
      <style>{`
        .cv-wrap { display: grid; grid-template-columns: 200px 1fr; gap: 1.25rem; }
        @media (max-width: 860px) { .cv-wrap { grid-template-columns: 1fr; } }
        .cv-rack { display:block; width:100%; text-align:left; padding:.5rem .7rem;
          border-radius:8px; border:1px solid transparent; background:none;
          color:var(--text2); cursor:pointer; font-size:.85rem; margin-bottom:2px; }
        .cv-rack:hover { background:var(--bg3); color:var(--text); }
        .cv-rack.active { background:var(--bg3); color:var(--text);
          border-color:var(--teal); }
        .cv-row { display:flex; align-items:center; gap:1rem; padding:.85rem 1rem;
          border-top:1px solid var(--border); }
        .cv-secret { font-family:var(--mono); font-size:.85rem; color:var(--teal);
          background:var(--bg3); padding:.35rem .6rem; border-radius:6px;
          word-break:break-all; }
        .cv-btn { background:var(--bg3); border:1px solid var(--border);
          border-radius:8px; padding:.35rem .6rem; cursor:pointer;
          color:var(--text2); display:inline-flex; align-items:center; gap:.35rem;
          font-size:.78rem; }
        .cv-btn:hover { background:var(--bg4); color:var(--text); }
        .cv-overlay { position:fixed; inset:0; background:rgba(0,0,0,.8);
          backdrop-filter:blur(6px); display:flex; align-items:center;
          justify-content:center; z-index:9999; }
        .cv-modal { background:var(--bg2); border:1px solid var(--border);
          border-radius:18px; width:min(460px, 92vw); padding:1.5rem;
          position:relative; }
      `}</style>

      {flash && (
        <div style={{ padding: '.6rem .8rem', borderRadius: 8, marginBottom: '1rem',
          background: 'rgba(34,197,94,.12)', fontSize: '.85rem' }}>
          <CheckCircle size={14} style={{ verticalAlign: -2, marginRight: 6 }} />
          {flash}
        </div>
      )}
      {error && (
        <div style={{ padding: '.6rem .8rem', borderRadius: 8, marginBottom: '1rem',
          background: 'rgba(239,68,68,.12)', fontSize: '.85rem' }}>
          <AlertCircle size={14} style={{ verticalAlign: -2, marginRight: 6 }} />
          {error}
        </div>
      )}

      {mfaEnrolled === false && <MfaPrompt onDone={() => setMfaEnrolled(true)} />}

      <div className="cv-wrap">
        <aside>
          <div style={{ fontSize: '.7rem', textTransform: 'uppercase',
            opacity: .6, marginBottom: '.5rem', fontFamily: 'var(--mono)' }}>
            Racks
          </div>
          {/* Always reachable, so a credential can never be invisible just
              because it sits in a rack that is not selected. */}
          <button
            className={`cv-rack ${activeRack === null ? 'active' : ''}`}
            onClick={() => setActiveRack(null)}
          >
            All credentials
          </button>
          {racks.map((r) => (
            <button
              key={r.id}
              className={`cv-rack ${activeRack === r.id ? 'active' : ''}`}
              onClick={() => setActiveRack(r.id)}
            >
              {r.name}
            </button>
          ))}
        </aside>

        <main>
          <div style={{ display: 'flex', gap: '.6rem', marginBottom: '1rem' }}>
            <div style={{ position: 'relative', flex: 1 }}>
              <Search size={14} style={{ position: 'absolute', left: 10, top: 10,
                opacity: .5 }} />
              <input
                className="form-input"
                placeholder="Search name, username or URL"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{ paddingLeft: 30, width: '100%' }}
              />
            </div>
            <button className="cv-btn" onClick={() => setShowCreate(true)}>
              <Plus size={14} /> New
            </button>
          </div>

          <div className="card-box" style={{ padding: 0 }}>
            {loading ? (
              <div style={{ padding: '2rem', opacity: .6 }}>Loading…</div>
            ) : items.length === 0 ? (
              <div style={{ padding: '2.5rem', textAlign: 'center', opacity: .6 }}>
                <KeyRound size={26} style={{ marginBottom: '.5rem' }} />
                <div style={{ fontSize: '.9rem' }}>Nothing here yet.</div>
              </div>
            ) : (
              items.map((item) => {
                const entry = revealed[item.id];
                return (
                  <div key={item.id} className="cv-row">
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 600, fontSize: '.92rem' }}>
                        {item.name}
                        {item.has_2fa && (
                          <Shield size={12} style={{ marginLeft: 6, opacity: .7,
                            verticalAlign: -1 }} />
                        )}
                      </div>
                      <div style={{ fontSize: '.76rem', opacity: .6 }}>
                        {item.username || '—'}{item.url ? ` · ${item.url}` : ''}
                      </div>
                      {entry && (
                        <div style={{ marginTop: '.5rem' }}>
                          <span className="cv-secret">{entry.secret}</span>
                          <span style={{ fontSize: '.7rem', opacity: .6,
                            marginLeft: '.6rem' }}>
                            hides in {entry.expiresIn}s
                          </span>
                          {entry.notes && (
                            <div style={{ fontSize: '.76rem', opacity: .7,
                              marginTop: '.35rem' }}>
                              {entry.notes}
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    <button className="cv-btn" onClick={() => handleReveal(item)}>
                      {entry ? <EyeOff size={13} /> : <Eye size={13} />}
                      {entry ? 'Hide' : 'Reveal'}
                    </button>
                    {entry && (
                      <button className="cv-btn" onClick={() => handleCopy(item)}>
                        <Copy size={13} /> Copy
                      </button>
                    )}
                    <a className="cv-btn" href={`/vault/credential/${item.id}`}
                      title="Sharing and activity">
                      <Share2 size={13} />
                    </a>
                    <button className="cv-btn" onClick={() => setDeleteTarget(item)}>
                      <Trash2 size={13} />
                    </button>
                  </div>
                );
              })
            )}
          </div>
        </main>
      </div>

      {pendingReveal && (
        <div className="cv-overlay">
          <form className="cv-modal" onSubmit={submitStepUp}>
            <button type="button" onClick={() => { setPendingReveal(null); setCode(''); }}
              style={{ position: 'absolute', top: 14, right: 14, background: 'none',
                border: 'none', color: 'var(--text3)', cursor: 'pointer' }}>
              <X size={18} />
            </button>
            <h3 style={{ marginTop: 0, fontSize: '1.05rem' }}>Confirm it's you</h3>
            <p style={{ fontSize: '.84rem', opacity: .75 }}>
              Revealing <strong>{pendingReveal.name}</strong> needs a code from your
              authenticator. This is recorded in the audit log.
            </p>
            <input
              className="form-input"
              autoFocus
              inputMode="numeric"
              maxLength={6}
              placeholder="000000"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
              style={{ width: '100%', fontFamily: 'var(--mono)', fontSize: '1.4rem',
                letterSpacing: '.3em', textAlign: 'center', padding: '.7rem' }}
            />
            <button type="submit" disabled={code.length < 6 || stepUpBusy}
              style={{ width: '100%', marginTop: '1rem', padding: '.7rem',
                borderRadius: 10, border: 'none', background: 'var(--teal)',
                color: '#fff', fontWeight: 600, cursor: 'pointer' }}>
              {stepUpBusy ? 'Checking…' : 'Reveal'}
            </button>
          </form>
        </div>
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
              setActiveRack(created.rack_id);   // the effect reloads
            } else {
              await loadItems();
            }
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
    if (!enrolment?.provisioning_uri || !canvasRef.current) return;
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
      borderLeft: '3px solid #f59e0b' }}>
      <h4 style={{ margin: '0 0 .4rem', fontSize: '.95rem' }}>
        Set up your authenticator
      </h4>
      <p style={{ fontSize: '.84rem', opacity: .75, marginTop: 0 }}>
        Revealing a secret needs a second factor. Enrol once, and you will only
        be asked for a code when you actually reveal something.
      </p>
      {err && (
        <div style={{ fontSize: '.8rem', color: '#ef4444', marginBottom: '.5rem' }}>
          {err}
        </div>
      )}

      {!enrolment ? (
        <button className="cv-btn" onClick={start}>Start setup</button>
      ) : (
        <div style={{ display: 'flex', gap: '1.25rem', flexWrap: 'wrap',
          alignItems: 'flex-start' }}>
          <div style={{ background: '#fff', padding: 8, borderRadius: 8 }}>
            <canvas ref={canvasRef} />
          </div>

          <div style={{ flex: 1, minWidth: 240 }}>
            <p style={{ fontSize: '.8rem', opacity: .8, marginTop: 0 }}>
              Scan this with Google Authenticator, 1Password, Authy or similar.
            </p>

            <div style={{ fontSize: '.72rem', opacity: .6, marginBottom: '.2rem' }}>
              Or enter this key by hand:
            </div>
            <div style={{ display: 'flex', gap: '.4rem', alignItems: 'center',
              marginBottom: '.8rem' }}>
              <code className="cv-secret" style={{ fontSize: '.78rem' }}>
                {grouped}
              </code>
              <button type="button" className="cv-btn"
                onClick={() => navigator.clipboard.writeText(enrolment.secret)}>
                <Copy size={12} />
              </button>
            </div>

            <form onSubmit={confirm}>
              <div style={{ fontSize: '.72rem', opacity: .6, marginBottom: '.25rem' }}>
                Then enter the 6-digit code it shows:
              </div>
              <div style={{ display: 'flex', gap: '.5rem' }}>
                <input
                  className="form-input"
                  autoFocus
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  placeholder="000000"
                  maxLength={6}
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                  style={{ fontFamily: 'var(--mono)', width: 120,
                    letterSpacing: '.15em' }}
                />
                <button className="cv-btn" type="submit"
                  disabled={code.length < 6 || busy}>
                  {busy ? 'Checking…' : 'Confirm'}
                </button>
              </div>
            </form>

            <div style={{ fontSize: '.7rem', opacity: .55, marginTop: '.6rem' }}>
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

  const strength = estimateStrength(form.secret);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const regenerate = () => {
    try { set('secret', generatePassword(opts)); }
    catch (e) { onError(e.message); }
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
    <div className="cv-overlay">
      <form className="cv-modal" onSubmit={submit}
        style={{ maxHeight: '90vh', overflowY: 'auto' }}>
        <button type="button" onClick={onClose} style={{ position: 'absolute',
          top: 14, right: 14, background: 'none', border: 'none',
          color: 'var(--text3)', cursor: 'pointer' }}>
          <X size={18} />
        </button>
        <h3 style={{ marginTop: 0, fontSize: '1.05rem' }}>New credential</h3>

        <label className="form-label">Rack</label>
        <select className="form-input" value={form.rack_id}
          onChange={(e) => set('rack_id', Number(e.target.value))}
          style={{ width: '100%', marginBottom: '.7rem' }}>
          {racks.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
        </select>

        <label className="form-label">Name</label>
        <input className="form-input" required value={form.name}
          onChange={(e) => set('name', e.target.value)}
          style={{ width: '100%', marginBottom: '.7rem' }} />

        <label className="form-label">Username</label>
        <input className="form-input" value={form.username}
          onChange={(e) => set('username', e.target.value)}
          style={{ width: '100%', marginBottom: '.7rem' }} />

        <label className="form-label">URL</label>
        <input className="form-input" value={form.url}
          onChange={(e) => set('url', e.target.value)}
          style={{ width: '100%', marginBottom: '.7rem' }} />

        <label className="form-label">Secret</label>
        <div style={{ display: 'flex', gap: '.4rem' }}>
          <input className="form-input" required value={form.secret}
            onChange={(e) => set('secret', e.target.value)}
            style={{ flex: 1, fontFamily: 'var(--mono)' }} />
          <button type="button" className="cv-btn" onClick={regenerate}>
            <RefreshCw size={13} /> Generate
          </button>
        </div>

        {form.secret && (
          <div style={{ marginTop: '.5rem' }}>
            <div style={{ height: 4, background: 'var(--bg3)', borderRadius: 2 }}>
              <div style={{ height: '100%', width: `${strength.percent}%`,
                background: toneColour, borderRadius: 2, transition: 'width .2s' }} />
            </div>
            <div style={{ fontSize: '.72rem', opacity: .75, marginTop: '.3rem' }}>
              {strength.label} · ~{strength.bits} bits of entropy
            </div>
          </div>
        )}

        <div style={{ display: 'flex', gap: '.8rem', flexWrap: 'wrap',
          fontSize: '.75rem', marginTop: '.6rem', opacity: .85 }}>
          <label>
            Length{' '}
            <input type="number" min={8} max={128} value={opts.length}
              onChange={(e) => setOpts({ ...opts, length: Number(e.target.value) })}
              style={{ width: 56 }} />
          </label>
          {['upper', 'digits', 'symbols'].map((k) => (
            <label key={k}>
              <input type="checkbox" checked={opts[k]}
                onChange={(e) => setOpts({ ...opts, [k]: e.target.checked })} />{' '}
              {k}
            </label>
          ))}
        </div>

        <label className="form-label" style={{ marginTop: '.7rem' }}>
          Notes (encrypted)
        </label>
        <textarea className="form-input" rows={2} value={form.notes}
          onChange={(e) => set('notes', e.target.value)}
          style={{ width: '100%' }} />

        <label style={{ display: 'block', fontSize: '.8rem', marginTop: '.6rem' }}>
          <input type="checkbox" checked={form.has_2fa}
            onChange={(e) => set('has_2fa', e.target.checked)} />{' '}
          This account has 2FA enabled
        </label>

        <button type="submit" disabled={busy}
          style={{ width: '100%', marginTop: '1rem', padding: '.7rem',
            borderRadius: 10, border: 'none', background: 'var(--teal)',
            color: '#fff', fontWeight: 600, cursor: 'pointer' }}>
          {busy ? 'Saving…' : 'Save credential'}
        </button>
      </form>
    </div>
  );
}
