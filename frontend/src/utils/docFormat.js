// src/utils/docFormat.js — formatting for the HR document screens.

export const ACTION_TEXT = {
  'letter.drafted': 'Drafted', 'letter.viewed': 'Opened', 'letter.edited': 'Edited',
  'letter.issued': 'Issued', 'letter.revoked': 'Revoked', 'letter.downloaded': 'Downloaded',
  'letter.acknowledged': 'Acknowledged by the employee', 'letter.discarded': 'Discarded',
  'policy.published': 'Published a version', 'policy.updated': 'Details changed',
  'policy.downloaded': 'Downloaded', 'policy.reminded': 'Reminders sent', 'policy.acknowledged': 'Acknowledged',
  'document.filed': 'Filed', 'document.renewed': 'Renewed', 'document.updated': 'Details changed',
  'document.downloaded': 'Downloaded', 'document.template_updated': 'Template edited',
  'document.templates_added': 'Template added',
};

export function fmtDateTime(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function fmtDate(iso) {
  if (!iso) return '—';
  const d = iso.length === 10 ? new Date(`${iso}T00:00:00`) : new Date(iso);
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

export function fmtSize(bytes) {
  if (!bytes) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
