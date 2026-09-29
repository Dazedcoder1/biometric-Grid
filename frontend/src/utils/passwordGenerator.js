/**
 * Password generation and strength estimation.
 *
 * Generated in the browser, deliberately: a password created here only reaches
 * the server when the user saves it. Generating server-side would put every
 * discarded candidate through the network and the request log for no benefit.
 *
 * Uses crypto.getRandomValues — the platform CSPRNG. Math.random() is a
 * non-cryptographic PRNG whose output is predictable from a few samples, and
 * it must never appear in this file.
 */

const LOWER = 'abcdefghijkmnopqrstuvwxyz';  // no 'l'
const UPPER = 'ABCDEFGHJKLMNPQRSTUVWXYZ';   // no 'I', no 'O'
const DIGITS = '23456789';                  // no '0', no '1'
const SYMBOLS = '!@#$%^&*-_=+?';

export const DEFAULTS = {
  length: 20,
  lower: true,
  upper: true,
  digits: true,
  symbols: true,
  avoidAmbiguous: true,
};

/**
 * A uniformly random integer in [0, max).
 *
 * Rejection sampling, not `value % max`. Modulo skews the distribution
 * whenever max does not divide 2^32 evenly — the low values become slightly
 * more likely. The bias is small but it is real, and discarding out-of-range
 * draws costs nothing.
 */
function randomInt(max) {
  const limit = Math.floor(0xffffffff / max) * max;
  const buf = new Uint32Array(1);
  let value;
  do {
    crypto.getRandomValues(buf);
    value = buf[0];
  } while (value >= limit);
  return value % max;
}

function pick(alphabet) {
  return alphabet[randomInt(alphabet.length)];
}

/** Fisher-Yates using the CSPRNG, so the guaranteed characters land anywhere. */
function shuffle(chars) {
  for (let i = chars.length - 1; i > 0; i -= 1) {
    const j = randomInt(i + 1);
    [chars[i], chars[j]] = [chars[j], chars[i]];
  }
  return chars;
}

export function generatePassword(options = {}) {
  const opts = { ...DEFAULTS, ...options };
  const ambiguous = opts.avoidAmbiguous;

  const pools = [];
  if (opts.lower) pools.push(ambiguous ? LOWER : LOWER + 'l');
  if (opts.upper) pools.push(ambiguous ? UPPER : UPPER + 'IO');
  if (opts.digits) pools.push(ambiguous ? DIGITS : DIGITS + '01');
  if (opts.symbols) pools.push(SYMBOLS);

  if (pools.length === 0) throw new Error('Select at least one character type.');

  const length = Math.max(opts.length, pools.length);

  // One character from each selected pool first, so the result always
  // satisfies a "must contain a digit and a symbol" policy. Relying on chance
  // means occasionally producing a password the target system rejects.
  const chars = pools.map(pick);

  const all = pools.join('');
  while (chars.length < length) chars.push(pick(all));

  return shuffle(chars).join('');
}

/**
 * Strength as entropy in bits, plus a label.
 *
 * Entropy from the alphabet actually used, not from a checklist of rules.
 * "P@ssw0rd!" satisfies every rule and is worthless; length and alphabet size
 * are what an offline attacker faces. This does not model dictionary attacks,
 * so it over-rates memorable passwords — which is one more reason to use the
 * generator rather than invent one.
 */
export function estimateStrength(password) {
  if (!password) return { bits: 0, label: 'Empty', percent: 0, tone: 'muted' };

  let alphabet = 0;
  if (/[a-z]/.test(password)) alphabet += 26;
  if (/[A-Z]/.test(password)) alphabet += 26;
  if (/[0-9]/.test(password)) alphabet += 10;
  if (/[^A-Za-z0-9]/.test(password)) alphabet += 32;

  const unique = new Set(password).size;
  let bits = password.length * Math.log2(alphabet || 1);

  // A long string of one repeated character has high nominal entropy and no
  // real strength. Scale by how much of it is actually distinct.
  if (unique < password.length / 2) {
    bits *= unique / (password.length / 2);
  }
  bits = Math.round(bits);

  let label;
  let tone;
  if (bits < 40) { label = 'Weak'; tone = 'danger'; }
  else if (bits < 60) { label = 'Fair'; tone = 'warning'; }
  else if (bits < 80) { label = 'Strong'; tone = 'success'; }
  else { label = 'Very strong'; tone = 'success'; }

  // 100 bits is the top of the scale — beyond that the difference stops
  // mattering against any realistic attacker.
  return { bits, label, tone, percent: Math.min(100, Math.round((bits / 100) * 100)) };
}
