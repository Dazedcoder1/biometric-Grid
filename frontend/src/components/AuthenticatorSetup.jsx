// src/components/AuthenticatorSetup.jsx
//
// Setting up an authenticator app — the second factor that revealing a secret
// asks for. Shared by the Vault page (as a banner) and by the reveal prompts
// on Vault and People (inside the dialog).
//
// It used to live only as a banner at the top of the Vault page. Clicking
// Reveal without having set it up opened a "Confirm it's you" prompt asking
// for a code from an app the person did not have — a dead end, since every
// code was refused with "No second factor is enrolled". The prompts now show
// this instead when there is nothing to take a code from.

import React, { useEffect, useRef, useState } from 'react';
import { Check, Copy } from 'lucide-react';

import { vaultApi } from '../services/api';

export default function AuthenticatorSetup({ onDone, inModal = false, intro }) {
  const [enrolment, setEnrolment] = useState(null);   // { secret, provisioning_uri }
  const [code, setCode] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const canvasRef = useRef(null);

  const start = async () => {
    setErr('');
    setBusy(true);
    try {
      setEnrolment(await vaultApi.beginEnrolment());
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
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
      setErr(
        /not correct|invalid/i.test(e2.message || '')
          ? `${e2.message} Codes change every 30 seconds — use the one showing now. If a fresh code is still refused, set your phone's clock to automatic.`
          : e2.message,
      );
      setCode('');
    } finally {
      setBusy(false);
    }
  };

  const copyKey = async () => {
    try {
      await navigator.clipboard.writeText(enrolment.secret);
      setCopied(true);
    } catch {
      setErr('Could not reach the clipboard — type the key in by hand.');
    }
  };

  // Grouped in fours. A 32-character base32 string typed off a screen in one
  // run is a transcription error waiting to happen.
  const grouped = enrolment?.secret
    ? enrolment.secret.match(/.{1,4}/g).join(' ')
    : '';

  const body = (
    <>
      <p style={{ fontSize: '.84rem', color: 'var(--text2)', marginTop: inModal ? '.4rem' : 0, lineHeight: 1.5 }}>
        {intro || 'Revealing a secret needs a second factor. Set it up once, and you will only be asked for a code when you actually reveal something.'}
      </p>
      {err && (
        <div role="alert" style={{ fontSize: '.8rem', color: '#f87171', marginBottom: '.6rem', lineHeight: 1.45 }}>
          {err}
        </div>
      )}

      {!enrolment ? (
        <button type="button" className={inModal ? 'v-btn-primary' : 'v-btn'} onClick={start} disabled={busy}>
          {busy ? 'Starting…' : 'Set up authenticator'}
        </button>
      ) : (
        <div style={{ display: 'flex', gap: '1.25rem', flexWrap: 'wrap', alignItems: 'flex-start' }}>
          {/* White plate on purpose: a QR needs light quiet zones to scan, and
              in dark mode the card background is not light enough. */}
          <div style={{ background: '#fff', padding: 8, borderRadius: 8 }}>
            <canvas ref={canvasRef} />
          </div>

          <div style={{ flex: 1, minWidth: 220 }}>
            <p style={{ fontSize: '.8rem', color: 'var(--text2)', marginTop: 0 }}>
              1. Scan this with Google Authenticator, Microsoft Authenticator,
              1Password, Authy or similar.
            </p>

            <div style={{ fontSize: '.72rem', color: 'var(--text3)', marginBottom: '.2rem' }}>
              Or enter this key by hand:
            </div>
            <div style={{ display: 'flex', gap: '.4rem', alignItems: 'center', marginBottom: '.8rem' }}>
              <code className="v-secret" style={{ fontSize: '.78rem' }}>{grouped}</code>
              <button type="button" className="v-btn" aria-label="Copy setup key" onClick={copyKey}>
                {copied ? <Check size={12} /> : <Copy size={12} />}
              </button>
            </div>

            <form onSubmit={confirm}>
              <div style={{ fontSize: '.8rem', color: 'var(--text2)', marginBottom: '.3rem' }}>
                2. Enter the 6-digit code it shows:
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
                  style={{ fontFamily: 'var(--mono)', width: 120, letterSpacing: '.15em' }}
                />
                <button className="v-btn" type="submit" disabled={code.length < 6 || busy}>
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
    </>
  );

  if (inModal) return body;

  return (
    <div className="card-box" style={{ marginBottom: '1.25rem', borderLeft: '3px solid var(--amber)' }}>
      <h4 style={{ margin: '0 0 .4rem', fontSize: '.95rem' }}>Set up your authenticator</h4>
      {body}
    </div>
  );
}
