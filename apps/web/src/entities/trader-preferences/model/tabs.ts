/** The Ideas tabs a trader can open on (ADR 0083): the stored default is one of these. */
export const IDEAS_TABS = ['stocks', 'premium'] as const;

export type IdeasTab = (typeof IDEAS_TABS)[number];

/** The most names a watchlist holds (the server refuses more). */
export const MAX_WATCHLIST = 50;

export const isIdeasTab = (value: unknown): value is IdeasTab =>
  typeof value === 'string' && (IDEAS_TABS as readonly string[]).includes(value);
