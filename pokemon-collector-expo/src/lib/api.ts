import { nameScore, parseCardText, type ScanClues } from './parser';
import type { ApiCard } from './types';

const BASE = 'https://api.pokemontcg.io/v2';
const FIELDS = 'id,name,number,rarity,supertype,hp,set,images,tcgplayer,cardmarket';
// Optional, for higher rate limits: free key from https://dev.pokemontcg.io, set as
// EXPO_PUBLIC_POKEMON_TCG_API_KEY in .env or as an EAS environment variable.
const API_KEY = process.env.EXPO_PUBLIC_POKEMON_TCG_API_KEY ?? '';

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** The public API returns sporadic 500/502s under load; a few quick retries clears most. */
async function get<T>(path: string, params: Record<string, string>): Promise<T> {
  const url = `${BASE}/${path}?${new URLSearchParams(params).toString()}`;
  const headers: Record<string, string> = API_KEY ? { 'X-Api-Key': API_KEY } : {};
  let lastStatus = 0;
  for (let attempt = 1; attempt <= 4; attempt++) {
    const res = await fetch(url, { headers });
    if (res.ok) return (await res.json()) as T;
    lastStatus = res.status;
    if (![429, 500, 502, 503, 504].includes(res.status)) break;
    await sleep(400 * attempt);
  }
  throw new Error(`Card database error (HTTP ${lastStatus})`);
}

async function search(q: string, pageSize = 30): Promise<ApiCard[]> {
  const r = await get<{ data: ApiCard[] }>('cards', {
    q, pageSize: String(pageSize), orderBy: '-set.releaseDate', select: FIELDS,
  });
  return r.data;
}

export async function getCard(id: string): Promise<ApiCard> {
  const r = await get<{ data: ApiCard }>(`cards/${encodeURIComponent(id)}`, { select: FIELDS });
  return r.data;
}

const clean = (s: string) => s.replace(/["\\]/g, '');

function rankByClues(cards: ApiCard[], clues: ScanClues): ApiCard[] {
  if (clues.names.length === 0 && clues.hp == null) return cards;
  const score = (c: ApiCard) =>
    Math.max(0, ...clues.names.map((n) => nameScore(n, c.name))) +
    (clues.hp != null && c.hp === String(clues.hp) ? 0.3 : 0);
  return [...cards].sort((a, b) => score(b) - score(a));
}

/** Best matches for what the camera read, most likely first. */
export async function identify(clues: ScanClues): Promise<ApiCard[]> {
  if (clues.number != null) {
    let q = `number:"${clues.number}"`;
    if (clues.setTotal != null) q += ` set.printedTotal:${clues.setTotal}`;
    let hits = await search(q);
    // The printed total is the part OCR most often garbles; retry on the number alone.
    if (hits.length === 0 && clues.setTotal != null) hits = await search(`number:"${clues.number}"`, 100);
    if (hits.length > 0) return rankByClues(hits, clues);
  }
  for (const name of clues.names.slice(0, 3)) {
    const hits = await search(`name:"${clean(name)}"`);
    if (hits.length > 0) return rankByClues(hits, clues);
  }
  return [];
}

/** Free-text search: a name ("charizard ex"), a number ("4/102"), or both. */
export async function searchCards(text: string): Promise<ApiCard[]> {
  const t = text.trim();
  if (!t) return [];
  const clues = parseCardText([t]);
  if (clues.number != null) {
    const name = t.replace(/\S*\d+\s*\/\s*\S*\d+\S*|(SWSH|SM|XY|BW)\s?\d+/g, '').trim();
    return identify({ ...clues, names: name ? [name] : [] });
  }
  // One unquoted prefix term per word: "charizard ex" -> name:charizard* name:ex*
  // (the API rejects wildcards inside quoted phrases).
  const terms = t.split(/\s+/).map((w) => w.replace(/[^\p{L}\p{N}'-]/gu, '')).filter(Boolean);
  if (terms.length === 0) return [];
  return search(terms.map((w) => `name:${w}*`).join(' '), 60);
}
