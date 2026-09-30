// src/utils/auditMeta.js
//
// Presentation for audit entries: what each category looks like, and how to
// group a page of entries by day.
//
// Wording stays on the server — the label and category come down with each
// row, so the phrasing cannot drift from what was actually recorded. This file
// only decides the icon and the colour.

import {
  Building2, Database, FileDown, KeyRound, Network, ShieldCheck, Users,
} from 'lucide-react';

export const CATEGORY_META = {
  credential: { icon: KeyRound,    label: 'Credential', tint: 'var(--teal)' },
  access:     { icon: Users,       label: 'Access',     tint: 'var(--info)' },
  auth:       { icon: ShieldCheck, label: 'Sign-in',    tint: '#a855f7' },
  structure:  { icon: Network,     label: 'Structure',  tint: 'var(--text3)' },
  audit:      { icon: FileDown,    label: 'Audit',      tint: 'var(--warn)' },
  // A Super Admin acting on the organisation from outside it — created,
  // renamed, key rotated. Rare, and worth being able to spot at a glance.
  platform:   { icon: Building2,   label: 'Platform',   tint: '#f472b6' },
  other:      { icon: Database,    label: 'Other',      tint: 'var(--text3)' },
};

export function categoryMeta(category) {
  return CATEGORY_META[category] || CATEGORY_META.other;
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
  if (filters.result) chips.push({ key: 'result', label: `result: ${filters.result}` });
  if (filters.actor_id) chips.push({ key: 'actor_id', label: `actor #${filters.actor_id}` });
  if (filters.since) chips.push({ key: 'since', label: `from ${filters.since}` });
  if (filters.until) chips.push({ key: 'until', label: `to ${filters.until}` });
  return chips;
}
