// src/utils/credentialMeta.js
//
// Turns the metadata the credential list already returns into things worth
// showing on a row.
//
// Every field used here comes from the existing /api/vault/credentials
// response — kind, has_2fa, expires_at, last_accessed_at, updated_at,
// owner_id. Nothing is inferred or invented, which matters on this screen:
// a credential list that overstates what it knows is worse than a plain one.

import {
  FileKey, Globe, KeyRound, ScrollText, Server, Shield,
} from 'lucide-react';

// The kinds the database CHECK constraint permits. Anything outside this set
// cannot be stored, so `other` is a fallback for old rows rather than a
// guess at unknown future types.
export const KINDS = [
  { value: 'password',    label: 'Password',    icon: KeyRound },
  { value: 'api_key',     label: 'API key',     icon: FileKey },
  { value: 'token',       label: 'Token',       icon: Shield },
  { value: 'ssh_key',     label: 'SSH key',     icon: Server },
  { value: 'certificate', label: 'Certificate', icon: ScrollText },
  { value: 'other',       label: 'Other',       icon: Globe },
];

const BY_VALUE = Object.fromEntries(KINDS.map((k) => [k.value, k]));

export function kindMeta(kind) {
  return BY_VALUE[kind] || BY_VALUE.other;
}

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** "3d", "2mo", "just now" — compact enough for a chip. */
export function relativeAge(iso) {
  if (!iso) return null;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;

  const ms = Date.now() - then;
  if (ms < MINUTE) return 'just now';
  if (ms < HOUR) return `${Math.floor(ms / MINUTE)}m`;
  if (ms < DAY) return `${Math.floor(ms / HOUR)}h`;

  const days = Math.floor(ms / DAY);
  if (days < 30) return `${days}d`;
  if (days < 365) return `${Math.floor(days / 30)}mo`;
  return `${Math.floor(days / 365)}y`;
}

/**
 * Expiry state for a credential.
 *
 * Returns null when no expiry is set, rather than inventing a default. A
 * credential with no expiry is a real and common choice here, and rendering
 * it as "expires never" in a warning colour would train people to ignore the
 * chip that matters.
 */
export function expiryStatus(expiresAt) {
  if (!expiresAt) return null;
  const when = new Date(expiresAt).getTime();
  if (Number.isNaN(when)) return null;

  const days = Math.ceil((when - Date.now()) / DAY);
  if (days < 0) return { tone: 'danger', label: `expired ${relativeAge(expiresAt)} ago` };
  if (days === 0) return { tone: 'danger', label: 'expires today' };
  if (days <= 7) return { tone: 'danger', label: `${days}d left` };
  if (days <= 30) return { tone: 'warn', label: `${days}d left` };
  return { tone: null, label: `${days}d left` };
}

/**
 * Whether this row reached the viewer through a share rather than ownership.
 *
 * The list endpoint returns owned and shared credentials in one array with no
 * flag distinguishing them, so this compares owner_id to the signed-in user.
 * If the user object has no id — which happens for the legacy API-key session,
 * where the token carries a tenant rather than a person — return false instead
 * of guessing, so nothing is mislabelled as someone else's.
 */
export function isSharedWithMe(credential, user) {
  const me = user?.id;
  if (me == null || credential?.owner_id == null) return false;
  return Number(credential.owner_id) !== Number(me);
}
