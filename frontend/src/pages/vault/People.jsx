// src/pages/vault/People.jsx
//
// Everyone's vault, one person at a time — yours first, then the people you
// administer. A Tenant Admin sees their whole organisation; an Org Admin sees
// the employees in their own department. The server decides who is listed.
//
// Sign-in passwords are not here and cannot be: they are stored as one-way
// hashes that nobody can read. What an admin CAN do is issue a temporary one
// (Reset sign-in password), which the person must replace at next sign-in.
//
// Safeguards for revealing someone else's secret, all enforced server-side:
//   * a fresh authenticator code (purpose 'credential.oversee');
//   * an audit entry written before the secret is decrypted;
//   * a notification to the owner, in the same transaction.
//
// Same two rules as the main vault screen: revealed secrets live in component
// state only, and hide themselves after 30 seconds.

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertCircle, AlertTriangle, Check, CheckCircle, Copy, Eye, EyeOff, KeyRound,
  Pencil, RefreshCw, Search, Shield, ShieldAlert, UserCog, Users, Wand2,
} from 'lucide-react';

import DashboardLayout from '../../layouts/DashboardLayout';
import VaultModal from '../../components/VaultModal';
import AuthenticatorSetup from '../../components/AuthenticatorSetup';
import { useAuth } from '../../context/AuthContext';
import usePermissions from '../../hooks/usePermissions';
import { accountsApi, vaultApi } from '../../services/api';
import { sidebarPropsFor } from '../../utils/sidebarRole';
import { generatePassword } from '../../utils/passwordGenerator';
import { expiryStatus, kindMeta, relativeAge } from '../../utils/credentialMeta';
import './vault.css';

const REVEAL_SECONDS = 30;

const ROLE_LABEL = { tenant_admin: 'Tenant Admin', org_admin: 'Org Admin', employee: 'Employee' };

/** A cached step-up token if it has not expired yet. Reads the clock, so it
 *  lives outside the component and is only ever called from event handlers. */
function liveToken(entry) {
  return entry && Date.now() < entry.expiry ? entry.token : null;
}

export default function People() {
  const { user } = useAuth();
  const { can, grantsAll, loading: permsLoading } = usePermissions();

  const [people, setPeople] = useState(null);
  const [filter, setFilter] = useState('');
  const [selectedId, setSelectedId] = useState(null);

  const [creds, setCreds] = useState(null);
  const [credsLoading, setCredsLoading] = useState(false);

  const [error, setError] = useState('');
  const [flash, setFlash] = useState('');
  const [mfaEnrolled, setMfaEnrolled] = useState(null);

  // id -> { secret, notes, expiresIn }
  const [revealed, setRevealed] = useState({});
  const [pendingReveal, setPendingReveal] = useState(null);
  const [code, setCode] = useState('');
  const [stepUpBusy, setStepUpBusy] = useState(false);
  // Inside the prompt — on the page it would sit behind the overlay.
  const [stepUpError, setStepUpError] = useState('');

  // One assertion per purpose: revealing your own uses 'credential.reveal',
  // someone else's 'credential.oversee'. The server binds each token to its
  // purpose, so they cannot stand in for each other.
  const tokens = useRef({});

  const [resetTarget, setResetTarget] = useState(null);
  // Super Admin only: putting a new password into someone's credential.
  const [changeTarget, setChangeTarget] = useState(null);

  const note = (msg) => { setFlash(msg); setTimeout(() => setFlash(''), 3500); };

  // The cached step-up tokens, offered to dialogs as functions rather than
  // the ref itself, so nothing outside this component writes into it.
  const tokenStore = {
    get: (purpose) => liveToken(tokens.current[purpose]),
    put: (purpose, token, expiresAt) => {
      tokens.current[purpose] = { token, expiry: new Date(expiresAt).getTime() - 1000 };
    },
    forget: (purpose) => { delete tokens.current[purpose]; },
  };

  // ─── load people ───────────────────────────────────────────────────────────

  const loadPeople = useCallback(() => vaultApi.oversightPeople().then(
    (rows) => { setPeople(rows); setError(''); },
    (err) => setError(err.message || 'Could not load people.'),
  ), []);

  useEffect(() => {
    let cancelled = false;
    vaultApi.oversightPeople().then(
      (rows) => {
        if (cancelled) return;
        setPeople(rows);
        // Start on yourself: always present, and never a notification.
        const me = rows.find((p) => p.is_me);
        setSelectedId(me ? me.id : rows[0]?.id ?? null);
      },
      (err) => { if (!cancelled) setError(err.message || 'Could not load people.'); },
    );
    vaultApi.mfaStatus().then(
      (s) => { if (!cancelled) setMfaEnrolled(!!s.enrolled); },
      () => { if (!cancelled) setMfaEnrolled(null); },
    );
    return () => { cancelled = true; };
  }, []);

  const selected = useMemo(
    () => (people || []).find((p) => p.id === selectedId) || null,
    [people, selectedId],
  );

  // ─── load the selected person's credentials ────────────────────────────────

  useEffect(() => {
    if (selectedId == null) return undefined;
    let cancelled = false;
    vaultApi.oversightCredentials(selectedId).then(
      (res) => {
        if (cancelled) return;
        setCreds(res.credentials);
        setCredsLoading(false);
      },
      (err) => {
        if (cancelled) return;
        setCreds([]);
        setCredsLoading(false);
        setError(err.message || 'Could not load this vault.');
      },
    );
    return () => { cancelled = true; };
  }, [selectedId]);

  const choose = (id) => {
    if (id === selectedId) return;
    // Nothing revealed for one person stays on screen when looking at another.
    setRevealed({});
    setCreds(null);
    setCredsLoading(true);
    setSelectedId(id);
  };

  // ─── auto-hide ─────────────────────────────────────────────────────────────

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

  const purposeFor = (person) => (person?.is_me ? 'credential.reveal' : 'credential.oversee');

  const freshToken = (purpose) => liveToken(tokens.current[purpose]);

  const doReveal = async (item, token) => {
    const data = selected?.is_me
      ? await vaultApi.reveal(item.id, token)
      : await vaultApi.oversightReveal(item.id, token);
    setRevealed((prev) => ({
      ...prev,
      [item.id]: { secret: data.secret, notes: data.notes, expiresIn: REVEAL_SECONDS },
    }));
    if (!selected?.is_me) note(`Revealed. ${selected.name} has been notified.`);
  };

  const handleReveal = async (item) => {
    if (revealed[item.id]) {
      setRevealed((prev) => { const n = { ...prev }; delete n[item.id]; return n; });
      return;
    }
    setError('');
    const token = freshToken(purposeFor(selected));
    if (token) {
      try { await doReveal(item, token); return; } catch (err) {
        if (!err.stepUpRequired) { setError(err.message); return; }
        delete tokens.current[purposeFor(selected)];
      }
    }
    setPendingReveal(item);
  };

  const submitStepUp = async (e) => {
    e.preventDefault();
    setStepUpBusy(true);
    setStepUpError('');
    const purpose = purposeFor(selected);
    try {
      const res = await vaultApi.stepUp(code.trim(), purpose);
      tokens.current[purpose] = {
        token: res.step_up_token,
        expiry: new Date(res.expires_at).getTime() - 1000,
      };
      await doReveal(pendingReveal, res.step_up_token);
      setPendingReveal(null);
      setCode('');
    } catch (err) {
      if ((err.message || '').includes('No second factor is enrolled')) {
        setMfaEnrolled(false);
      } else {
        setStepUpError(
          /not correct/i.test(err.message || '')
            ? 'That code is not correct. Codes change every 30 seconds — use the one showing now. If a fresh code is still refused, set your phone\'s clock to automatic.'
            : (err.message || 'That code was not accepted.'),
        );
      }
      setCode('');
    } finally {
      setStepUpBusy(false);
    }
  };

  const handleCopy = async (item) => {
    const entry = revealed[item.id];
    if (!entry) return;
    try {
      await navigator.clipboard.writeText(entry.secret);
      note('Copied.');
      // Your own: recorded like any copy. Someone else's: the reveal is already
      // in the audit log and the owner already notified — the copy endpoint
      // checks shares, which an administrator does not hold.
      if (selected?.is_me) vaultApi.recordCopy(item.id).catch(() => {});
    } catch {
      setError('Could not reach the clipboard. Select the value and copy it manually.');
    }
  };

  // ─── derived ───────────────────────────────────────────────────────────────

  const visiblePeople = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return people || [];
    return (people || []).filter((p) => [p.name, p.email, p.employee_code, p.department]
      .some((v) => v && String(v).toLowerCase().includes(q)));
  }, [people, filter]);

  const canOversee = can('credential.oversee');
  const canReset = can('user.password_reset');
  const others = (people || []).filter((p) => !p.is_me).length;

  // ─── render ────────────────────────────────────────────────────────────────

  return (
    <DashboardLayout title="People" {...sidebarPropsFor(user)}>
      <style>{`
        .v-people { grid-template-columns: 270px 1fr; }
        @media (max-width: 860px) { .v-people { grid-template-columns: 1fr; } }
        .v-person { flex-direction: column; align-items: stretch; gap: .2rem; text-align: left; }
        .v-person-top { display: flex; align-items: center; gap: .45rem; }
        .v-person-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .v-person-sub { font-size: .72rem; color: var(--text3); }
      `}</style>

      {flash && (
        <div className="v-banner ok"><CheckCircle size={14} /><span>{flash}</span></div>
      )}
      {error && (
        <div className="v-banner bad" role="alert"><AlertCircle size={14} /><span>{error}</span></div>
      )}

      {!permsLoading && !canOversee && (
        <div className="v-banner warn">
          <AlertTriangle size={14} />
          <span>Your role does not include looking after other people&apos;s vaults.</span>
        </div>
      )}

      {mfaEnrolled === false && (
        <div className="v-banner warn">
          <ShieldAlert size={14} />
          <span>
            Revealing anything needs an authenticator app. You haven&apos;t set one up yet —
            press Reveal on any password and it will walk you through it.
          </span>
        </div>
      )}

      <div className="v-wrap v-people">
        {/* ─── people ─────────────────────────────────────────────────────── */}
        <aside>
          <div className="v-racks-label">
            People {people && `· ${others} you look after`}
          </div>
          {people && people.length > 6 && (
            <div style={{ position: 'relative', marginBottom: '.5rem' }}>
              <Search size={13} style={{ position: 'absolute', left: 10, top: '50%',
                transform: 'translateY(-50%)', color: 'var(--text3)' }} />
              <input
                className="form-input"
                placeholder="Name, email, code, department"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                style={{ paddingLeft: 30, width: '100%' }}
                aria-label="Filter people"
              />
            </div>
          )}

          <div className="v-racks">
            {people === null && !error && (
              <div className="v-person-sub" style={{ padding: '.5rem' }}>Loading…</div>
            )}
            {visiblePeople.map((p) => (
              <button
                key={p.id}
                type="button"
                className={`v-rack v-person ${p.id === selectedId ? 'active' : ''}`}
                onClick={() => choose(p.id)}
                aria-current={p.id === selectedId ? 'true' : undefined}
              >
                <span className="v-person-top">
                  <span className="v-person-name">{p.is_me ? `${p.name} (you)` : p.name}</span>
                  <span className="v-rack-count" title="Credentials in their vault">{p.credential_count}</span>
                </span>
                <span className="v-person-sub">
                  {ROLE_LABEL[p.role] || p.role}
                  {p.department ? ` · ${p.department}` : ''}
                  {!p.is_active ? ' · inactive' : ''}
                  {p.must_change_password ? ' · temporary password' : ''}
                </span>
              </button>
            ))}
            {people && visiblePeople.length === 0 && (
              <div className="v-person-sub" style={{ padding: '.5rem' }}>Nobody matches.</div>
            )}
          </div>
        </aside>

        {/* ─── one person's vault ─────────────────────────────────────────── */}
        <main>
          {selected && (
            <div className="card-box" style={{ padding: '1rem 1.1rem', marginBottom: '1rem',
              display: 'flex', alignItems: 'center', gap: '.8rem', flexWrap: 'wrap' }}>
              <div className="v-kind" style={{ background: 'rgba(0,212,170,0.12)', color: 'var(--teal)' }}>
                {selected.is_me ? <KeyRound size={16} /> : <Users size={16} />}
              </div>
              <div style={{ flex: 1, minWidth: 180 }}>
                <div style={{ fontWeight: 600, color: 'var(--text)' }}>
                  {selected.is_me ? 'Your vault' : `${selected.name}'s vault`}
                </div>
                <div style={{ fontSize: '.76rem', color: 'var(--text3)' }}>
                  {[selected.email, selected.employee_code, ROLE_LABEL[selected.role], selected.department]
                    .filter(Boolean).join(' · ')}
                </div>
              </div>
              {!selected.is_me && canReset && (
                <button type="button" className="v-btn" onClick={() => setResetTarget(selected)}>
                  <UserCog size={13} /> Reset sign-in password
                </button>
              )}
            </div>
          )}

          {selected && !selected.is_me && (
            <div className="v-banner warn">
              <Eye size={14} />
              <span>
                Revealing a password here asks for your authenticator code, is written to the
                audit log, and notifies {selected.name}.
              </span>
            </div>
          )}

          <div className="card-box" style={{ padding: 0, overflow: 'hidden' }}>
            {(credsLoading || (selected && creds === null)) ? (
              <div className="v-empty"><div className="v-empty-body">Loading…</div></div>
            ) : !selected ? (
              <div className="v-empty"><div className="v-empty-body">Choose someone on the left.</div></div>
            ) : creds.length === 0 ? (
              <div className="v-empty">
                <div className="v-empty-icon"><KeyRound size={22} /></div>
                <div className="v-empty-title">Nothing stored</div>
                <div className="v-empty-body">
                  {selected.is_me ? 'You have' : `${selected.name} has`} no credentials in their vault.
                </div>
              </div>
            ) : (
              creds.map((item) => (
                <PersonCredentialRow
                  key={item.id}
                  item={item}
                  entry={revealed[item.id]}
                  canReveal={selected.is_me ? can('credential.reveal') : canOversee}
                  canChange={grantsAll && !selected.is_me}
                  onReveal={() => handleReveal(item)}
                  onCopy={() => handleCopy(item)}
                  onChange={() => setChangeTarget({
                    ...item, hadToken: !!tokenStore.get('credential.oversee'),
                  })}
                />
              ))
            )}
          </div>
        </main>
      </div>

      {pendingReveal && (
        <VaultModal
          title={mfaEnrolled === false ? 'Set up your authenticator' : "Confirm it's you"}
          onClose={() => { setPendingReveal(null); setCode(''); setStepUpError(''); }}
        >
          {mfaEnrolled === false ? (
            <AuthenticatorSetup
              inModal
              intro={`Revealing "${pendingReveal.name}" needs a code from an authenticator app on your phone. You haven't set one up yet — it takes a minute, and you only do it once.`}
              onDone={() => { setMfaEnrolled(true); setStepUpError(''); }}
            />
          ) : (
          <form onSubmit={submitStepUp}>
            <p style={{ fontSize: '.84rem', color: 'var(--text2)', marginTop: '.4rem', lineHeight: 1.5 }}>
              Revealing <strong style={{ color: 'var(--text)' }}>{pendingReveal.name}</strong>
              {selected && !selected.is_me
                ? <> from <strong style={{ color: 'var(--text)' }}>{selected.name}</strong>&apos;s vault. They will be notified, and it is recorded in the audit log.</>
                : '. This is recorded in the audit log.'}
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
            {stepUpError && (
              <div role="alert" style={{ fontSize: '.8rem', color: '#f87171', marginTop: '.6rem', lineHeight: 1.45 }}>
                {stepUpError}
              </div>
            )}
            <button type="submit" className="v-btn-primary" disabled={code.length < 6 || stepUpBusy}>
              {stepUpBusy ? 'Checking…' : 'Reveal'}
            </button>
          </form>
          )}
        </VaultModal>
      )}

      {changeTarget && selected && (
        <ChangePasswordModal
          item={changeTarget}
          person={selected}
          tokenStore={tokenStore}
          mfaEnrolled={mfaEnrolled}
          onEnrolled={() => setMfaEnrolled(true)}
          onClose={() => setChangeTarget(null)}
          onDone={(res) => {
            setChangeTarget(null);
            // Whatever was revealed for it is now the old value.
            setRevealed((prev) => { const n = { ...prev }; delete n[changeTarget.id]; return n; });
            note(`Password changed. ${selected.name} has been notified.`
              + (res.update_these_systems?.length
                ? ` Update: ${res.update_these_systems.join(', ')}.` : ''));
          }}
        />
      )}

      {resetTarget && (
        <ResetPasswordModal
          person={resetTarget}
          onClose={() => setResetTarget(null)}
          onDone={() => { loadPeople(); }}
        />
      )}
    </DashboardLayout>
  );
}

// ─── one credential ──────────────────────────────────────────────────────────

function PersonCredentialRow({ item, entry, canReveal, canChange, onReveal, onCopy, onChange }) {
  const { icon: KindIcon, label: kindLabel } = kindMeta(item.kind);
  const expiry = expiryStatus(item.expires_at);
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
            <Shield size={12} style={{ color: 'var(--text3)' }} aria-label="This account has 2FA enabled" />
          )}
        </div>
        <div className="v-row-sub">
          {item.username || 'No username'}
          {item.url ? ` · ${item.url}` : ''}
        </div>
        <div className="v-chips">
          <span className="v-chip">{kindLabel}</span>
          {expiry && <span className={`v-chip ${expiry.tone || ''}`}>{expiry.label}</span>}
          <span className="v-chip">{lastUsed ? `used ${lastUsed} ago` : 'never used'}</span>
        </div>
        {entry && (
          <div style={{ marginTop: '.6rem', maxWidth: 420 }}>
            <span className="v-secret">{entry.secret}</span>
            <div className="v-countdown">
              <div className="v-countdown-fill" style={{ width: `${(entry.expiresIn / REVEAL_SECONDS) * 100}%` }} />
            </div>
            <div style={{ fontSize: '.7rem', color: 'var(--text3)', marginTop: '.25rem' }}>
              Hides in {entry.expiresIn}s
            </div>
            {entry.notes && (
              <div style={{ fontSize: '.76rem', color: 'var(--text2)', marginTop: '.4rem', whiteSpace: 'pre-wrap' }}>
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
        {canChange && (
          <button type="button" className="v-btn" onClick={onChange} title="Set a new password">
            <Pencil size={13} /> Change
          </button>
        )}
      </div>
    </div>
  );
}

// ─── change a saved password (Super Admin) ───────────────────────────────────

function ChangePasswordModal({ item, person, tokenStore, mfaEnrolled, onEnrolled, onClose, onDone }) {
  const PURPOSE = 'credential.oversee';
  const [secret, setSecret] = useState('');
  const [show, setShow] = useState(false);
  const [code, setCode] = useState('');
  const [needsCode, setNeedsCode] = useState(!item.hadToken);
  const [impact, setImpact] = useState(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setErr('');
    try {
      let token = tokenStore.get(PURPOSE);
      if (!token) {
        const res = await vaultApi.stepUp(code.trim(), PURPOSE);
        token = res.step_up_token;
        tokenStore.put(PURPOSE, token, res.expires_at);
        setNeedsCode(false);
      }
      const res = await vaultApi.oversightChange(item.id, token, secret, acknowledged);
      onDone(res);
    } catch (e2) {
      if (e2.status === 409 && e2.detail?.error === 'impact_acknowledgement_required') {
        // Production systems still hold the old value. Say which, and ask.
        setImpact(e2.detail.impact);
      } else if (e2.stepUpRequired) {
        tokenStore.forget(PURPOSE);
        setNeedsCode(true);
        setErr('Enter a fresh code from your authenticator.');
      } else if ((e2.message || '').includes('No second factor is enrolled')) {
        setErr('');
      } else {
        setErr(e2.message || 'The password could not be changed.');
      }
      setCode('');
    } finally {
      setBusy(false);
    }
  };

  if (mfaEnrolled === false) {
    return (
      <VaultModal title="Set up your authenticator" onClose={onClose}>
        <AuthenticatorSetup
          inModal
          intro="Changing someone's saved password needs a code from an authenticator app. You haven't set one up yet — it takes a minute, and you only do it once."
          onDone={onEnrolled}
        />
      </VaultModal>
    );
  }

  const ready = secret.length > 0 && (!needsCode || code.length === 6)
    && (!impact || acknowledged);

  return (
    <VaultModal title="Change saved password" onClose={onClose}>
      <p style={{ fontSize: '.84rem', color: 'var(--text2)', marginTop: '.4rem', lineHeight: 1.5 }}>
        New password for <strong style={{ color: 'var(--text)' }}>{item.name}</strong> in{' '}
        <strong style={{ color: 'var(--text)' }}>{person.name}</strong>&apos;s vault. They will be
        notified, it is recorded in the audit log, and the old value is kept as an
        earlier version.
      </p>
      <form onSubmit={submit}>
        <label className="form-label" htmlFor="chg-secret">New password</label>
        <div style={{ display: 'flex', gap: '.4rem', marginBottom: '.8rem' }}>
          <input
            id="chg-secret"
            className="form-input"
            type={show ? 'text' : 'password'}
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            autoComplete="new-password"
            autoFocus
            style={{ flex: 1, fontFamily: show ? 'var(--mono)' : undefined }}
          />
          <button type="button" className="v-btn" onClick={() => setShow((s) => !s)}
            aria-label={show ? 'Hide password' : 'Show password'}>
            {show ? <EyeOff size={13} /> : <Eye size={13} />}
          </button>
          <button type="button" className="v-btn" title="Generate a strong password"
            onClick={() => { setSecret(generatePassword()); setShow(true); }}>
            <Wand2 size={13} />
          </button>
        </div>

        {needsCode && (
          <>
            <label className="form-label" htmlFor="chg-code">Code from your authenticator</label>
            <input
              id="chg-code"
              className="form-input"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              placeholder="000000"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
              style={{ width: '100%', fontFamily: 'var(--mono)', fontSize: '1.2rem',
                letterSpacing: '.3em', textAlign: 'center' }}
            />
          </>
        )}

        {impact && (
          <div className="v-banner warn" style={{ marginTop: '.8rem', marginBottom: 0, flexDirection: 'column', alignItems: 'stretch' }}>
            <div style={{ display: 'flex', gap: 6 }}>
              <AlertTriangle size={14} />
              <span>{impact.summary} Each must be updated with the new password:</span>
            </div>
            <ul style={{ margin: '.4rem 0 .4rem 1.4rem', padding: 0 }}>
              {impact.systems.map((s) => (
                <li key={s.system_id}>{s.name}{s.environment ? ` (${s.environment})` : ''}{s.is_production ? ' — production' : ''}</li>
              ))}
            </ul>
            <label style={{ display: 'flex', gap: 6, alignItems: 'center', cursor: 'pointer' }}>
              <input type="checkbox" checked={acknowledged} onChange={(e) => setAcknowledged(e.target.checked)} />
              I&apos;ll update these — change it anyway
            </label>
          </div>
        )}

        {err && (
          <div role="alert" style={{ fontSize: '.8rem', color: '#f87171', marginTop: '.6rem' }}>{err}</div>
        )}

        <button type="submit" className="v-btn-primary" disabled={!ready || busy}>
          {busy ? 'Saving…' : 'Change password'}
        </button>
      </form>
    </VaultModal>
  );
}

// ─── reset sign-in password ──────────────────────────────────────────────────

function ResetPasswordModal({ person, onClose, onDone }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [copied, setCopied] = useState(false);

  const reset = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await accountsApi.resetPassword(person.id);
      setResult(res);
      onDone();
    } catch (err) {
      setError(err.message || 'The password could not be reset.');
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(result.temporary_password);
      setCopied(true);
    } catch {
      setError('Could not reach the clipboard. Select the password and copy it manually.');
    }
  };

  return (
    <VaultModal title="Reset sign-in password" onClose={onClose}>
      {error && (
        <div className="v-banner bad" role="alert" style={{ marginTop: '.6rem' }}>
          <AlertCircle size={14} /><span>{error}</span>
        </div>
      )}

      {!result ? (
        <>
          <p style={{ fontSize: '.85rem', color: 'var(--text2)', lineHeight: 1.55, marginTop: '.5rem' }}>
            Nobody can see <strong style={{ color: 'var(--text)' }}>{person.name}</strong>&apos;s
            current password — it is stored so it cannot be read back. This gives them a new,
            temporary one instead.
          </p>
          <ul style={{ fontSize: '.82rem', color: 'var(--text2)', lineHeight: 1.6, paddingLeft: '1.1rem', margin: '.4rem 0 0' }}>
            <li>Their current password stops working immediately.</li>
            <li>They are signed out everywhere.</li>
            <li>At next sign-in they must choose their own password.</li>
            <li>It is recorded in the audit log, and they are notified.</li>
          </ul>
          <div style={{ display: 'flex', gap: '.5rem', marginTop: '1.2rem' }}>
            <button type="button" className="v-btn" onClick={onClose} style={{ flex: 1, justifyContent: 'center' }}>
              Cancel
            </button>
            <button type="button" className="btn btn-red" onClick={reset} disabled={busy} style={{ flex: 1 }}>
              <RefreshCw size={13} style={{ marginRight: 6 }} />
              {busy ? 'Resetting…' : 'Reset password'}
            </button>
          </div>
        </>
      ) : (
        <>
          <div className="v-banner ok" style={{ marginTop: '.6rem' }}>
            <CheckCircle size={14} /><span>{result.message}</span>
          </div>
          <div className="form-label" style={{ marginBottom: '.35rem' }}>Temporary password</div>
          <div style={{ display: 'flex', gap: '.4rem' }}>
            <code className="v-secret" style={{ flex: 1, minWidth: 0, overflowWrap: 'anywhere' }}>
              {result.temporary_password}
            </code>
            <button type="button" className="v-btn" onClick={copy}>
              {copied ? <Check size={13} /> : <Copy size={13} />} {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
          <div className="v-banner warn" style={{ marginTop: '.7rem', marginBottom: 0 }}>
            <AlertTriangle size={14} />
            <span>
              Shown once. Give it to {person.name} directly — in person or by phone, not in a
              group chat. They sign in with{' '}
              <code style={{ fontFamily: 'var(--mono)' }}>
                {result.user.email || result.user.employee_code}
              </code>.
            </span>
          </div>
          <button type="button" className="v-btn-primary" onClick={onClose}>Done</button>
        </>
      )}
    </VaultModal>
  );
}
