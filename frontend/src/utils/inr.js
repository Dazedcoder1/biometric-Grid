// src/utils/inr.js — rupee amounts with Indian digit grouping (12,34,567.00).

const FMT = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
const FMT2 = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** ₹38,000 or ₹1,234.50 — paise only when there are some. */
export function inr(value) {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  if (Number.isNaN(n)) return '—';
  return `${n < 0 ? '-' : ''}₹${FMT.format(Math.abs(n))}`;
}

/** Always two decimals — registers and totals. */
export function inr2(value) {
  const n = Number(value || 0);
  return `${n < 0 ? '-' : ''}₹${FMT2.format(Math.abs(n))}`;
}

/** 2026-10 -> "October 2026". */
export function monthLabel(period) {
  if (!period) return '';
  const [y, m] = period.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString('en-IN', { month: 'long', year: 'numeric', timeZone: 'UTC' });
}
