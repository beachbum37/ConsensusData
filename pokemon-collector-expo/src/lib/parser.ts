/** What could be read off a card photo. */
export type ScanClues = {
  /** Collector number in API form: "25", "TG05", "SWSH050". */
  number: string | null;
  /** Printed set size from "025/198", when the number is a plain numeric one. */
  setTotal: number | null;
  hp: number | null;
  /** Possible card names, most likely first. */
  names: string[];
};

// "025/198", "4/102", "TG05/TG30", "GG01/GG70", "201/198".
// OCR often reads 0 as O and 1 as I or l, so those are accepted inside the digits.
const SLASH_NUMBER =
  /(?<![A-Za-z0-9])([A-Z]{0,3}?)([0-9OIl]{1,3})\s*\/\s*([A-Z]{0,3}?)([0-9OIl]{2,3})(?![0-9])/g;

// Black Star promos printed without a slash: "SWSH050", "SM60", "XY124", "BW45".
const PROMO_NUMBER = /(?<![A-Za-z])(SWSH|SM|XY|BW)\s?(\d{2,3})(?!\d)/;

const HP = /(?:HP\s*(\d{2,3}))|(?:(\d{2,3})\s*HP)/i;
const HP_ALL = new RegExp(HP.source, 'gi');

const NAME_CHARS = /^[A-Za-zÀ-ÿ'’.\- ♀♂]+$/;

/** Card furniture that is never a card name. */
const STOP_WORDS = new Set([
  'basic', 'stage', 'stage 1', 'stage 2', 'evolves from', 'trainer', 'item', 'supporter',
  'stadium', 'energy', 'pokémon tool', 'pokemon tool', 'weakness', 'resistance',
  'retreat', 'retreat cost', 'illus', 'pokémon', 'pokemon', 'ability', 'poké-power',
  'poké-body', 'tera', 'rule', 'length', 'weight', 'nintendo', 'creatures',
  'game freak', 'special energy', 'basic energy', 'v rule', 'vmax rule', 'ex rule',
  'put', 'attach', 'flip', 'discard', 'search', 'draw', 'your', 'this', 'the',
  'damage', 'opponent', "opponent's", 'active', 'bench', 'benched', 'heads', 'tails',
]);

export function isEmpty(c: ScanClues) {
  return c.number == null && c.names.length === 0;
}

/** Identity used to decide whether two photos saw the same card. */
export function cluesKey(c: ScanClues) {
  return c.number != null ? `#${c.number}/${c.setTotal ?? ''}` : `n:${(c.names[0] ?? '').toLowerCase()}`;
}

export function describe(c: ScanClues) {
  return [
    c.names[0],
    c.number != null ? (c.setTotal != null ? `${c.number}/${c.setTotal}` : c.number) : undefined,
    c.hp != null ? `HP ${c.hp}` : undefined,
  ].filter(Boolean).join(' · ');
}

/** Turns raw OCR lines (top-to-bottom) from a Pokémon card into lookup clues. */
export function parseCardText(lines: string[]): ScanClues {
  const text = lines.join('\n');
  const [number, setTotal] = findNumber(text);
  const m = HP.exec(text);
  const hp = m ? parseInt(m[1] || m[2], 10) : null;
  return { number, setTotal, hp: Number.isNaN(hp) ? null : hp, names: findNames(lines) };
}

function fixDigits(s: string): string {
  const out = s.replace(/O/g, '0').replace(/[Il]/g, '1');
  return /^\d+$/.test(out) ? out : '';
}

function findNumber(text: string): [string | null, number | null] {
  for (const m of text.matchAll(SLASH_NUMBER)) {
    let [, prefix, rawNum, totalPrefix, rawTotal] = m;
    // A "prefix" made only of O/I is a misread digit ("IO2" is 102), not a subset code.
    if (/^[OI]*$/.test(prefix)) { rawNum = prefix + rawNum; prefix = ''; }
    if (/^[OI]*$/.test(totalPrefix)) { rawTotal = totalPrefix + rawTotal; totalPrefix = ''; }
    const num = fixDigits(rawNum);
    const tot = fixDigits(rawTotal);
    if (!num || !tot) continue;
    // Subset numbering (TG05/TG30): the API keeps the prefix and padding.
    if (prefix) return [prefix + num, null];
    const n = parseInt(num, 10);
    const t = parseInt(tot, 10);
    // Secret rares can run well past the printed total (Paldean Fates: 245/091).
    if (n === 0 || t < 2 || n > 400) continue;
    return [String(n), totalPrefix ? null : t];
  }
  const promo = PROMO_NUMBER.exec(text);
  if (promo) return [promo[1] + promo[2], null];
  return [null, null];
}

function findNames(lines: string[]): string[] {
  const out: string[] = [];
  for (const raw of lines) {
    // "Pikachu HP60" / "Charizard ex 330 HP" -> drop the HP part.
    const line = raw.replace(HP_ALL, ' ').replace(/\s+/g, ' ').trim();
    if (line.length < 3 || line.length > 28) continue;
    if (!NAME_CHARS.test(line)) continue;
    const lower = line.toLowerCase();
    if (STOP_WORDS.has(lower)) continue;
    if ([...STOP_WORDS].some((w) => w.length > 4 && lower.startsWith(w + ' '))) continue;
    if ((line.match(/\p{L}/gu) ?? []).length < 3) continue;
    // Rules text is long sentences; names are at most a few words.
    if (line.split(' ').length > 4) continue;
    if (!out.includes(line)) out.push(line);
    if (out.length >= 5) break;
  }
  return out;
}

/** Fuzzy name match in [0,1], tolerant of OCR slips and "ex"/"V" suffix noise. */
export function nameScore(a: string, b: string): number {
  const norm = (s: string) => s.toLowerCase().replace(/é/g, 'e').replace(/[^\p{L}\p{N}]/gu, '');
  const x = norm(a);
  const y = norm(b);
  if (!x || !y) return 0;
  if (x === y) return 1;
  if (x.startsWith(y) || y.startsWith(x)) return 0.9;
  return 1 - levenshtein(x, y) / Math.max(x.length, y.length);
}

function levenshtein(a: string, b: string): number {
  let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    for (let j = 1; j <= b.length; j++) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    }
    prev = cur;
  }
  return prev[b.length];
}
