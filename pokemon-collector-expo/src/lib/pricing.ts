import type { ApiCard } from './types';

export type VariantPrice = {
  variant: string;
  label: string;
  market: number | null;
  low: number | null;
  mid: number | null;
  high: number | null;
};

/** Display order: most common prints first. */
const ORDER = [
  'normal', 'holofoil', 'reverseHolofoil',
  '1stEditionNormal', '1stEditionHolofoil', 'unlimitedHolofoil', 'unlimited',
];

const LABELS: Record<string, string> = {
  normal: 'Normal',
  holofoil: 'Holofoil',
  reverseHolofoil: 'Reverse Holo',
  '1stEditionNormal': '1st Edition',
  '1stEditionHolofoil': '1st Edition Holo',
  unlimitedHolofoil: 'Unlimited Holo',
  unlimited: 'Unlimited',
};

export function variantLabel(v: string): string {
  return LABELS[v] ?? v.replace(/([a-z])([A-Z])/g, '$1 $2').replace(/^./, (c) => c.toUpperCase());
}

const rank = (v: string) => (ORDER.indexOf(v) < 0 ? ORDER.length : ORDER.indexOf(v));

/** TCGplayer prices (USD) for every variant the card is printed in. */
export function variants(card: ApiCard): VariantPrice[] {
  return Object.entries(card.tcgplayer?.prices ?? {})
    .map(([variant, p]) => ({
      variant,
      label: variantLabel(variant),
      market: p.market ?? null,
      low: p.low ?? null,
      mid: p.mid ?? null,
      high: p.high ?? null,
    }))
    .sort((a, b) => rank(a.variant) - rank(b.variant));
}

/** Default variant to record when the user adds a card. */
export function defaultVariant(card: ApiCard): string {
  const vs = variants(card);
  return vs.find((v) => v.market != null)?.variant ?? vs[0]?.variant ?? 'normal';
}

/**
 * Typical market value in USD for [variant]: TCGplayer market price, falling back to
 * TCGplayer mid, then any other variant's market price. Null when the card has no USD data.
 */
export function marketUsd(card: ApiCard, variant: string): number | null {
  const p = card.tcgplayer?.prices?.[variant];
  const direct = p?.market ?? p?.mid;
  if (direct != null) return direct;
  for (const v of variants(card)) {
    const x = v.market ?? v.mid;
    if (x != null) return x;
  }
  return null;
}

/** Cardmarket (European) trend price in EUR, as a second opinion. */
export function trendEur(card: ApiCard, variant: string): number | null {
  const p = card.cardmarket?.prices;
  if (!p) return null;
  const v = (variant === 'reverseHolofoil' ? p.reverseHoloTrend : p.trendPrice) ?? p.trendPrice ?? p.averageSellPrice;
  return v != null && v > 0 ? v : null;
}
