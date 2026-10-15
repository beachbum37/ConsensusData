import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { getCard } from './api';
import { marketUsd, trendEur } from './pricing';
import type { ApiCard, OwnedCard } from './types';

const STORAGE_KEY = 'collection.v1';

type CollectionApi = {
  items: OwnedCard[];
  loaded: boolean;
  add: (card: ApiCard, variant: string, quantity?: number) => void;
  setQuantity: (key: string, quantity: number) => void;
  /** Re-fetches market prices for everything. Resolves to how many cards updated. */
  refreshPrices: () => Promise<number>;
};

const Ctx = createContext<CollectionApi | null>(null);

function priced(item: OwnedCard, card: ApiCard, now: number): OwnedCard {
  return {
    ...item,
    priceUsd: marketUsd(card, item.variant),
    priceEur: trendEur(card, item.variant),
    tcgplayerUrl: card.tcgplayer?.url,
    priceUpdatedAt: now,
  };
}

export function CollectionProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<OwnedCard[]>([]);
  const [loaded, setLoaded] = useState(false);
  const itemsRef = useRef(items);
  useEffect(() => { itemsRef.current = items; }, [items]);

  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY)
      .then((raw) => { if (raw) setItems(JSON.parse(raw)); })
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  useEffect(() => {
    // Don't overwrite saved data with the empty initial state before it has loaded.
    if (loaded) AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(items)).catch(() => {});
  }, [items, loaded]);

  const add = useCallback((card: ApiCard, variant: string, quantity = 1) => {
    const now = Date.now();
    const key = `${card.id}|${variant}`;
    setItems((prev) => {
      const existing = prev.find((i) => i.key === key);
      if (existing) {
        return prev.map((i) => (i.key === key ? priced({ ...i, quantity: i.quantity + quantity }, card, now) : i));
      }
      const fresh: OwnedCard = {
        key,
        cardId: card.id,
        name: card.name,
        number: card.number,
        setName: card.set.name,
        setTotal: card.set.printedTotal,
        rarity: card.rarity,
        imageSmall: card.images.small,
        variant,
        quantity,
        priceUsd: null,
        priceEur: null,
        priceUpdatedAt: now,
        addedAt: now,
      };
      return [priced(fresh, card, now), ...prev];
    });
  }, []);

  const setQuantity = useCallback((key: string, quantity: number) => {
    setItems((prev) =>
      quantity <= 0 ? prev.filter((i) => i.key !== key) : prev.map((i) => (i.key === key ? { ...i, quantity } : i)),
    );
  }, []);

  const refreshPrices = useCallback(async () => {
    const ids = [...new Set(itemsRef.current.map((i) => i.cardId))];
    const fresh = new Map<string, ApiCard>();
    for (const id of ids) {
      try { fresh.set(id, await getCard(id)); } catch { /* keep the old price */ }
    }
    if (ids.length > 0 && fresh.size === 0) throw new Error('Price service unreachable');
    const now = Date.now();
    setItems((prev) => prev.map((i) => { const c = fresh.get(i.cardId); return c ? priced(i, c, now) : i; }));
    return fresh.size;
  }, []);

  const value = useMemo(() => ({ items, loaded, add, setQuantity, refreshPrices }), [items, loaded, add, setQuantity, refreshPrices]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useCollection(): CollectionApi {
  const v = useContext(Ctx);
  if (!v) throw new Error('useCollection outside CollectionProvider');
  return v;
}
