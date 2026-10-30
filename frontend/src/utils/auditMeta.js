// src/utils/auditMeta.js
//
// Presentation for audit entries: what each category looks like, and how to
// group a page of entries by day.
//
// Wording stays on the server — the label and category come down with each
// row, so the phrasing cannot drift from what was actually recorded. This file
// only decides the icon and the colour.

import {
  Building2, CalendarDays, CheckSquare, ClipboardList, Cpu, Database, FileDown, FileText, IndianRupee, KeyRound,
  Network, ShieldCheck, UserCog, Users,
} from 'lucide-react';

// Order here is the order of the category filter on the audit page.
// Tints are theme variables (vault.css): the bright values that read on the
// dark theme are close to invisible on white.
export const CATEGORY_META = {
  auth:       { icon: ShieldCheck,  label: 'Sign-in',           tint: 'var(--cat-auth)' },
  people:     { icon: UserCog,      label: 'People',            tint: 'var(--cat-people)' },
  attendance: { icon: CalendarDays, label: 'Leave & attendance', tint: 'var(--cat-attendance)' },
  devices:    { icon: Cpu,          label: 'Devices',           tint: 'var(--cat-devices)' },
  tasks:      { icon: CheckSquare,  label: 'Tasks',             tint: 'var(--cat-tasks)' },
  payroll:    { icon: IndianRupee,  label: 'Payroll',           tint: 'var(--cat-payroll)' },
  documents:  { icon: FileText,     label: 'HR documents',      tint: 'var(--cat-documents)' },
  reporting:  { icon: ClipboardList, label: 'Reports & targets',  tint: 'var(--cat-reporting)' },
  credential: { icon: KeyRound,     label: 'Credential',        tint: 'var(--teal)' },
  access:     { icon: Users,        label: 'Access',            tint: 'var(--info)' },
  structure:  { icon: Network,      label: 'Structure',         tint: 'var(--text3)' },
  audit:      { icon: FileDown,     label: 'Audit',             tint: 'var(--warn)' },
  // A Super Admin acting on the organisation from outside it — created,
  // renamed, key rotated. Rare, and worth being able to spot at a glance.
  platform:   { icon: Building2,    label: 'Platform',          tint: 'var(--cat-platform)' },
  other:      { icon: Database,     label: 'Other',             tint: 'var(--text3)' },
};

export function categoryMeta(category) {
  return CATEGORY_META[category] || CATEGORY_META.other;
}

/**
 * Who acted, in words. An entry with no person behind it is not "System":
 * it was an API key (which names an organisation, not a person), or a
 * sign-in attempt by someone who never proved who they were.
 */
export function actorText(entry) {
  if (entry.actor_name) return entry.actor_name;
  if (entry.actor_id) return `User #${entry.actor_id}`;
  if (entry.actor_role === 'api_key') return 'API key';
  if (entry.actor_role === 'unknown') return 'Someone';
  return 'System';
}

/**
 * What an entry was about, by name where the entry recorded one, so a row
 * reads "approved leave · Aarti Deshpande" rather than "leave 41".
 */
export function targetText(entry) {
  const d = entry.details || {};
  const name = d.name || d.employee || d.title || d.repo || d.account
    || (entry.target_type === 'device' ? entry.target_id : null);
  if (name) return String(name);
  if (entry.target_type) return `${entry.target_type.replace('_', ' ')} ${entry.target_id ?? ''}`.trim();
  return '';
}

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;

/** Clock time within a day group — the day is already in the header. */
export function timeOfDay(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? '--:--'
    : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/** "4m ago", "2h ago" — only used for today, where it beats a clock time. */
export function shortAgo(iso) {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const ms = Date.now() - then;
  if (ms < MINUTE) return 'just now';
  if (ms < HOUR) return `${Math.floor(ms / MINUTE)}m ago`;
  if (ms < 12 * HOUR) return `${Math.floor(ms / HOUR)}h ago`;
  return timeOfDay(iso);
}

/**
 * Day heading for a group.
 *
 * Uses the viewer's local day boundaries, which is what people mean by
 * "yesterday" — comparing UTC dates puts a 9pm local entry on the wrong day
 * for anyone west of Greenwich.
 */
export function dayHeading(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 'Unknown date';

  const startOfDay = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const days = Math.round((startOfDay(new Date()) - startOfDay(d)) / 86_400_000);

  if (days === 0) return 'Today';
  if (days === 1) return 'Yesterday';
  if (days < 7) return d.toLocaleDateString([], { weekday: 'long' });
  return d.toLocaleDateString([], {
    weekday: 'short', day: 'numeric', month: 'short',
    ...(d.getFullYear() === new Date().getFullYear() ? {} : { year: 'numeric' }),
  });
}

/**
 * Split entries into day groups, preserving the server's ordering.
 *
 * The server returns newest first and this walks that order without sorting,
 * so the grouping cannot silently reorder a log whose whole value is its
 * sequence. Entries arriving out of order would produce two groups for the
 * same day rather than being quietly merged — visible, which is the right
 * failure for an audit trail.
 */
export function groupByDay(entries) {
  const groups = [];
  let current = null;

  for (const entry of entries) {
    const heading = dayHeading(entry.occurred_at);
    if (!current || current.heading !== heading) {
      current = { heading, key: `${heading}-${entry.seq}`, entries: [] };
      groups.push(current);
    }
    current.entries.push(entry);
  }
  return groups;
}

/** Human summary of which filters are on, for removable chips. */
export function activeFilterChips(filters, actions) {
  const chips = [];
  if (filters.action) {
    const known = actions.find((a) => a.action === filters.action);
    chips.push({ key: 'action', label: known ? known.label : filters.action });
  }
  if (filters.category) chips.push({ key: 'category', label: categoryMeta(filters.category).label });
  if (filters.result) chips.push({ key: 'result', label: `result: ${filters.result}` });
  if (filters.actor_id) chips.push({ key: 'actor_id', label: `actor #${filters.actor_id}` });
  if (filters.since) chips.push({ key: 'since', label: `from ${filters.since}` });
  if (filters.until) chips.push({ key: 'until', label: `to ${filters.until}` });
  return chips;
}
