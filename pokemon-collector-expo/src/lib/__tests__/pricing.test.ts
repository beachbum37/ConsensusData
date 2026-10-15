/// <reference types="node" />
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { defaultVariant, marketUsd, trendEur } from '../pricing.ts';
import type { ApiCard } from '../types.ts';

const card = (prices: Record<string, object>, cm?: object): ApiCard => ({
  id: 'x-1', name: 'X', number: '1',
  set: { id: 'x', name: 'X', series: '', printedTotal: 1, total: 1, releaseDate: '' },
  images: { small: '', large: '' },
  tcgplayer: { prices },
  cardmarket: cm ? { prices: cm } : undefined,
});

test('picks requested variant', () => {
  const c = card({ normal: { market: 0.25 }, reverseHolofoil: { market: 1.1 } });
  assert.equal(marketUsd(c, 'reverseHolofoil'), 1.1);
  assert.equal(defaultVariant(c), 'normal');
});

test('falls back to mid, then another variant', () => {
  const c = card({ holofoil: { mid: 3 }, normal: { market: 1 } });
  assert.equal(marketUsd(c, 'holofoil'), 3);
  assert.equal(marketUsd(c, '1stEditionHolofoil'), 1);
});

test('no USD data', () => assert.equal(marketUsd(card({}), 'normal'), null));

test('cardmarket trend', () => {
  const c = card({}, { trendPrice: 2.5, reverseHoloTrend: 4 });
  assert.equal(trendEur(c, 'reverseHolofoil'), 4);
  assert.equal(trendEur(c, 'normal'), 2.5);
});
