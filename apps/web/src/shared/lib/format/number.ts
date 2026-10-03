/** Number formatting for display: fixed decimals, percentages and signed changes (en-US). */

const cache = new Map<string, Intl.NumberFormat>();

function formatter(options: Intl.NumberFormatOptions): Intl.NumberFormat {
  const key = JSON.stringify(options);
  let found = cache.get(key);
  if (!found) {
    found = new Intl.NumberFormat('en-US', options);
    cache.set(key, found);
  }
  return found;
}

/** Placeholder for a missing value (never `NaN` or an empty cell). */
export const MISSING = '—';

const isMissing = (value: number | null | undefined): value is null | undefined =>
  value === null || value === undefined || Number.isNaN(value);

/** `1234.5` -> `1,234.50`. */
export function formatNumber(value: number | null | undefined, decimals = 2): string {
  if (isMissing(value)) return MISSING;
  return formatter({ minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(
    value,
  );
}

/** A ratio as a percentage: `0.1234` -> `12.34%`. */
export function formatPercent(value: number | null | undefined, decimals = 2): string {
  if (isMissing(value)) return MISSING;
  return formatter({
    style: 'percent',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

/** A ratio as a signed percentage change: `0.0124` -> `+1.24%`, `-0.0087` -> `-0.87%`. */
export function formatSignedPercent(value: number | null | undefined, decimals = 2): string {
  if (isMissing(value)) return MISSING;
  return formatter({
    style: 'percent',
    signDisplay: 'exceptZero',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}
