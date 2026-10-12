// src/utils/clockFormat.js
//
// Formatting for the sign-in clock. Times are shown in the organisation's
// time zone (the server sends it with every response), not the viewer's
// browser zone — a manager travelling abroad should still see that someone
// signed in at 09:02, not at 05:32.

/** 31,500 -> "8h 45m". Zero reads as "0m", never as an empty string. */
export function fmtDuration(seconds) {
  const s = Math.max(0, Math.floor(seconds || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h ? `${h}h ${String(m).padStart(2, '0')}m` : `${m}m`;
}

/** 31,512 -> "08:45:12" — the running timer. */
export function fmtTimer(seconds) {
  const s = Math.max(0, Math.floor(seconds || 0));
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(Math.floor(s / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
}

function safeZone(tz) {
  try {
    if (tz) new Intl.DateTimeFormat('en', { timeZone: tz });
    return tz || undefined;
  } catch {
    return undefined;
  }
}

/** ISO instant -> "09:02 AM" in the organisation's zone. */
export function fmtTime(iso, tz) {
  if (!iso) return '';
  return new Date(iso).toLocaleTimeString('en-IN', {
    hour: '2-digit', minute: '2-digit', hour12: true, timeZone: safeZone(tz),
  }).toUpperCase(); // en-IN writes "am"/"pm"; match the big clock's "PM"
}

/** Live wall clock: { time: "10:42:07", ampm: "AM", date: "Mon, 12 Oct" }. */
export function wallClock(ms, tz) {
  const d = new Date(ms);
  const zone = safeZone(tz);
  const parts = d.toLocaleTimeString('en-IN', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true, timeZone: zone,
  }).split(' ');
  return {
    time: parts[0],
    ampm: (parts[1] || '').toUpperCase(),
    date: d.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', timeZone: zone }),
  };
}

/** "2026-10-12" -> "Mon, 12 Oct". The date string is already local. */
export function fmtDay(isoDate) {
  const [y, m, d] = isoDate.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('en-IN', {
    weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC',
  });
}

export const SOURCE_LABEL = { web: 'Web', device: 'Scanner' };
