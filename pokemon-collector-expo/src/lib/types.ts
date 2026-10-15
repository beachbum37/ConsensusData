export type TcgPrice = {
  low?: number | null;
  mid?: number | null;
  high?: number | null;
  market?: number | null;
  directLow?: number | null;
};

export type ApiCard = {
  id: string;
  name: string;
  number: string;
  rarity?: string;
  supertype?: string;
  hp?: string;
  set: {
    id: string;
    name: string;
    series: string;
    printedTotal: number;
    total: number;
    releaseDate: string;
  };
  images: { small: string; large: string };
  tcgplayer?: {
    url?: string;
    updatedAt?: string;
    /** Keyed by print variant: normal, holofoil, reverseHolofoil, 1stEditionHolofoil, ... */
    prices?: Record<string, TcgPrice>;
  };
  cardmarket?: {
    url?: string;
    updatedAt?: string;
    prices?: {
      averageSellPrice?: number | null;
      lowPrice?: number | null;
      trendPrice?: number | null;
      reverseHoloTrend?: number | null;
    };
  };
};

/** One line in the collection: a card in a particular print variant, with a count. */
export type OwnedCard = {
  key: string; // `${cardId}|${variant}`
  cardId: string;
  name: string;
  number: string;
  setName: string;
  setTotal: number;
  rarity?: string;
  imageSmall: string;
  variant: string;
  quantity: number;
  /** Latest known market value per copy, USD. */
  priceUsd: number | null;
  /** Cardmarket trend per copy, EUR. */
  priceEur: number | null;
  tcgplayerUrl?: string;
  priceUpdatedAt: number;
  addedAt: number;
};
