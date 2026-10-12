// src/pages/documents/Letters.jsx
//
// Every letter the organisation has written: drafts, issued, revoked.
// "New letter" picks a template and a person, fills what the app knows
// (name, designation, department, CTC, salary table…), asks for the rest,
// and saves a draft. A draft can be edited and previewed as a PDF; issuing
// numbers it, freezes it and puts it in the person's My Documents.

import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertCircle, Ban, Download, FilePlus2, FileText, Send, Trash2,
} from 'lucide-react';

import DashboardLayout from '../../layouts/DashboardLayout';
import VaultModal from '../../components/VaultModal';
import { useAuth } from '../../context/AuthContext';
import usePermissions from '../../hooks/usePermissions';
import { documentsApi } from '../../services/api';
import { sidebarPropsFor } from '../../utils/sidebarRole';
import { AccessLogButton, Pill, PersonSelect } from './shared';
import { fmtDate } from '../../utils/docFormat';

function highlight(text) {
  // Show any {{field}} still in the text so nobody issues a letter with a hole in it.
  const parts = (text || '').split(/(\{\{\s*[a-z_][a-z0-9_]*\s*\}\})/g);
  return parts.map((p, i) => (/^\{\{/.test(p) ? <span key={i} className="ph">{p}</span> : <React.Fragment key={i}>{p}</React.Fragment>));
}

function NewLetter({ templates, people, onClose, onCreated }) {
  const [templateId, setTemplateId] = useState('');
  const [userId, setUserId] = useState('');
  const [letterDate, setLetterDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [prep, setPrep] = useState(null);
  const [values, setValues] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!templateId || !userId) return undefined;
    let cancelled = false;
    documentsApi.prepareLetter({ template_id: Number(templateId), user_id: Number(userId), letter_date: letterDate }).then(
      (p) => { if (!cancelled) { setPrep(p); setError(''); } },
      (err) => { if (!cancelled) { setPrep(null); setError(err.message); } },
    );
    return () => { cancelled = true; };
  }, [templateId, userId, letterDate]);

  const create = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      onCreated(await documentsApi.createLetter({
        template_id: Number(templateId), user_id: Number(userId), letter_date: letterDate, values,
      }));
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  const active = templates.filter((t) => t.active);

  return (
    <VaultModal title="New letter" onClose={onClose} width={720}>
      <form onSubmit={create} style={{ marginTop: '.8rem' }}>
        <div className="pr-form three">
          <label className="pr-field">
            <span>Template</span>
            <select value={templateId} required onChange={(e) => setTemplateId(e.target.value)}>
              <option value="">Choose…</option>
              {active.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </label>
          <label className="pr-field">
            <span>For</span>
            <PersonSelect people={people} value={userId} onChange={setUserId} required />
          </label>
          <label className="pr-field">
            <span>Letter date</span>
            <input type="date" required value={letterDate} onChange={(e) => setLetterDate(e.target.value)} />
          </label>
        </div>

        {active.length === 0 && (
          <div className="v-banner warn" style={{ marginTop: '1rem' }}><AlertCircle size={14} />
            <span>No templates yet. Open Letter templates and add the starter set.</span></div>
        )}

        {prep && (
          <>
            {prep.needs.length > 0 && (
              <>
                <h4 style={{ margin: '1.1rem 0 .5rem', fontSize: '.88rem' }}>Fill in</h4>
                <div className="pr-form three">
                  {prep.needs.map((f) => (
                    <label key={f.name} className="pr-field">
                      <span>{f.label}</span>
                      <input type={f.type === 'date' ? 'date' : f.type === 'number' ? 'number' : 'text'}
                        value={values[f.name] || ''}
                        onChange={(e) => setValues({ ...values, [f.name]: e.target.value })} />
                    </label>
                  ))}
                </div>
                <p className="pr-sub" style={{ marginTop: '.4rem' }}>
                  You can leave something blank and add it while editing the draft — it cannot be issued until every field is filled.
                </p>
              </>
            )}
            <h4 style={{ margin: '1.1rem 0 .5rem', fontSize: '.88rem' }}>Filled in from records</h4>
            <div className="pr-lines" style={{ paddingTop: 0 }}>
              <div>
                {Object.entries(prep.auto).map(([k, v]) => (
                  <div key={k} className="pr-line"><span>{prep.template.fields.find((f) => f.name === k)?.label || k}</span><b>{String(v)}</b></div>
                ))}
                {prep.has_salary_table && (
                  <div className="pr-line"><span>Salary table</span>
                    <b>{prep.salary_table ? `${prep.salary_table.length} components` : 'No salary structure — add one under Salaries'}</b></div>
                )}
              </div>
            </div>
          </>
        )}

        {error && <div className="v-banner bad" style={{ marginTop: '1rem' }}><AlertCircle size={14} /><span>{error}</span></div>}
        <div className="pr-actions">
          <button type="button" className="v-btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="pr-btn-primary" disabled={busy || !prep}>
            <FilePlus2 size={14} /> {busy ? 'Creating…' : 'Create draft'}
          </button>
        </div>
      </form>
    </VaultModal>
  );
}

function LetterView({ id, onClose, onChanged }) {
  const { can } = usePermissions();
  const manage = can('documents.manage');
  const [x, setX] = useState(null);
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [revoking, setRevoking] = useState(false);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    documentsApi.letter(id).then(
      (l) => { if (!cancelled) { setX(l); setSubject(l.subject); setBody(l.body); } },
      (err) => { if (!cancelled) setError(err.message); },
    );
    return () => { cancelled = true; };
  }, [id]);

  const act = async (label, fn, after) => {
    setBusy(label);
    setError('');
    try {
      const r = await fn();
      if (r && r.id) { setX(r); setSubject(r.subject); setBody(r.body ?? body); }
      onChanged();
      after?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const dirty = x && (subject !== x.subject || body !== x.body);
  const draft = x?.status === 'draft';

  return (
    <VaultModal title={x ? `${x.kind_label} — ${x.employee}` : 'Letter'} onClose={onClose} width={820}>
      {x && (
        <>
          <div className="pr-head" style={{ margin: '.3rem 0 .8rem' }}>
            <Pill value={x.status} />
            <span className="pr-sub">
              {x.reference_no ? `${x.reference_no} · ` : ''}{fmtDate(x.letter_date)}
              {x.issued_by ? ` · issued by ${x.issued_by}` : ''}
              {x.acknowledged_at ? ` · acknowledged ${fmtDate(x.acknowledged_at)}` : ''}
            </span>
          </div>
          {x.status === 'revoked' && (
            <div className="v-banner bad"><Ban size={14} /><span>Revoked: {x.revoke_reason}</span></div>
          )}
          {draft && x.missing.length > 0 && (
            <div className="v-banner warn"><AlertCircle size={14} />
              <span>Still to fill in before issuing: {x.missing.join(', ')}. Replace the highlighted placeholders in the text.</span></div>
          )}

          {draft && manage ? (
            <>
              <label className="pr-field" style={{ marginBottom: '.6rem' }}>
                <span>Subject</span>
                <input value={subject} maxLength={200} onChange={(e) => setSubject(e.target.value)} />
              </label>
              <label className="pr-field">
                <span>Letter text</span>
                <textarea className="doc-editor" value={body} onChange={(e) => setBody(e.target.value)} />
                <small>**bold**, a blank line for a new paragraph. {'{{salary_table}}'} on its own line prints the salary table.</small>
              </label>
            </>
          ) : (
            <>
              <h4 style={{ margin: '0 0 .5rem' }}>{x.subject}</h4>
              <div className="doc-letter">{highlight(x.body)}</div>
            </>
          )}

          {error && <div className="v-banner bad" style={{ marginTop: '1rem' }}><AlertCircle size={14} /><span>{error}</span></div>}

          <div className="pr-actions" style={{ justifyContent: 'space-between' }}>
            <div className="doc-card-actions">
              <button type="button" className="v-btn" onClick={() => act('pdf', () => documentsApi.downloadLetter(x.id))}>
                <Download size={13} /> {draft ? 'Preview PDF' : 'Download PDF'}
              </button>
              <AccessLogButton targetType="letter" targetId={x.id} title={x.subject} />
            </div>
            {manage && (
              <div className="doc-card-actions">
                {draft && (
                  <>
                    <button type="button" className="v-btn danger" disabled={!!busy}
                      onClick={() => { if (window.confirm('Discard this draft?')) act('del', () => documentsApi.deleteLetter(x.id), onClose); }}>
                      <Trash2 size={13} /> Discard
                    </button>
                    <button type="button" className="v-btn" disabled={!dirty || !!busy}
                      onClick={() => act('save', () => documentsApi.editLetter(x.id, { subject, body }))}>
                      {busy === 'save' ? 'Saving…' : 'Save draft'}
                    </button>
                    <button type="button" className="pr-btn-primary" disabled={dirty || !!busy}
                      title={dirty ? 'Save your changes first' : undefined}
                      onClick={() => {
                        if (window.confirm(`Issue this letter to ${x.employee}? It is numbered, frozen and appears in their documents.`)) {
                          act('issue', () => documentsApi.issueLetter(x.id));
                        }
                      }}>
                      <Send size={14} /> {busy === 'issue' ? 'Issuing…' : 'Issue letter'}
                    </button>
                  </>
                )}
                {x.status === 'issued' && !revoking && (
                  <button type="button" className="v-btn danger" onClick={() => setRevoking(true)}><Ban size={13} /> Revoke</button>
                )}
              </div>
            )}
          </div>
          {revoking && (
            <form className="card-box" style={{ marginTop: '.8rem', marginBottom: 0, padding: '.9rem' }}
              onSubmit={(e) => { e.preventDefault(); act('revoke', () => documentsApi.revokeLetter(x.id, reason), () => setRevoking(false)); }}>
              <label className="pr-field">
                <span>Why is it being withdrawn? The employee sees this.</span>
                <input autoFocus required minLength={3} maxLength={255} value={reason} onChange={(e) => setReason(e.target.value)} />
              </label>
              <div className="pr-actions">
                <button type="button" className="v-btn" onClick={() => setRevoking(false)}>Cancel</button>
                <button type="submit" className="pr-btn-primary danger" disabled={!!busy}>Revoke letter</button>
              </div>
            </form>
          )}
        </>
      )}
      {!x && error && <div className="v-banner bad"><AlertCircle size={14} /><span>{error}</span></div>}
    </VaultModal>
  );
}

export default function Letters() {
  const { user } = useAuth();
  const { can } = usePermissions();
  const [rows, setRows] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [people, setPeople] = useState([]);
  const [status, setStatus] = useState('');
  const [query, setQuery] = useState('');
  const [error, setError] = useState('');
  const [creating, setCreating] = useState(false);
  const [open, setOpen] = useState(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    Promise.all([documentsApi.letters({ status }), documentsApi.templates(), documentsApi.people()]).then(
      ([l, t, p]) => { if (!cancelled) { setRows(l); setTemplates(t); setPeople(p); setError(''); } },
      (err) => { if (!cancelled) setError(err.message); },
    );
    return () => { cancelled = true; };
  }, [status, tick]);

  const list = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (rows || []).filter((r) => !q || (r.employee || '').toLowerCase().includes(q)
      || r.subject.toLowerCase().includes(q) || (r.reference_no || '').toLowerCase().includes(q));
  }, [rows, query]);

  return (
    <DashboardLayout title="Letters" {...sidebarPropsFor(user)}>
      <div className="pr-head">
        <div>
          <h2>Letters</h2>
          <div className="pr-sub">Offer, appointment, internship, confirmation, promotion, salary revision, experience and relieving letters.</div>
        </div>
        <span className="grow" />
        {can('documents.manage') && (
          <button type="button" className="pr-btn-primary" onClick={() => setCreating(true)}>
            <FilePlus2 size={14} /> New letter
          </button>
        )}
      </div>
      {error && <div className="v-banner bad"><AlertCircle size={14} /><span>{error}</span></div>}

      <div className="ct-toolbar">
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
          <option value="">All letters</option>
          <option value="draft">Drafts</option>
          <option value="issued">Issued</option>
          <option value="revoked">Revoked</option>
        </select>
        <input type="search" placeholder="Search person, subject or reference" aria-label="Search" value={query}
          onChange={(e) => setQuery(e.target.value)}
          style={{ height: 38, padding: '0 .7rem', borderRadius: 8, border: '1px solid var(--border2)', background: 'var(--bg2)', color: 'var(--text)', minWidth: 260 }} />
      </div>

      <div className="ct-table-wrap">
        <table className="ct-table">
          <thead><tr><th>Person</th><th>Letter</th><th>Reference</th><th>Date</th><th>Status</th><th>Received</th></tr></thead>
          <tbody>
            {!rows && !error && <tr><td colSpan={6} className="ct-empty">Loading…</td></tr>}
            {rows && list.length === 0 && <tr><td colSpan={6} className="ct-empty">No letters yet.</td></tr>}
            {list.map((r) => (
              <tr key={r.id} className="expandable" onClick={() => setOpen(r.id)}>
                <td className="strong">{r.employee}</td>
                <td><FileText size={12} style={{ verticalAlign: '-2px', marginRight: 5, color: 'var(--text3)' }} />{r.subject}
                  <div className="ct-sub">{r.kind_label}</div></td>
                <td className="mono">{r.reference_no || '—'}</td>
                <td className="mono">{fmtDate(r.letter_date)}</td>
                <td><Pill value={r.status} /></td>
                <td>{r.status === 'issued' ? (r.acknowledged_at ? fmtDate(r.acknowledged_at) : <span className="ct-sub">Not yet</span>) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {creating && (
        <NewLetter templates={templates} people={people} onClose={() => setCreating(false)}
          onCreated={(l) => { setCreating(false); setTick((n) => n + 1); setOpen(l.id); }} />
      )}
      {open && <LetterView id={open} onClose={() => setOpen(null)} onChanged={() => setTick((n) => n + 1)} />}
    </DashboardLayout>
  );
}
