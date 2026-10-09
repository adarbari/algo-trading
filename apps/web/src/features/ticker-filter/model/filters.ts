/** The security-type words the ticker views share: `COMMON_STOCK` is a Stock. */

const TYPE_WORDS: Readonly<Record<string, string>> = {
  COMMON_STOCK: 'Stock',
  ETF: 'ETF',
  ADR: 'ADR',
};

/** The type in words: `COMMON_STOCK` -> `Stock`, `PREFERRED_STOCK` -> `Preferred stock`. */
export function typeLabel(type: string): string {
  const known = TYPE_WORDS[type];
  if (known) return known;
  const words = type.replace(/_/g, ' ').toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}
