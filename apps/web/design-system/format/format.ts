/**
 * Value formatting for the data components (DataTable cells, KeyValue, StatStrip, BarList):
 * one place that decides how a number, percent, amount, date or change reads, so every screen
 * shows `$13.99B`, `72.1%` and `+1.24%` the same way. Pure functions, en-US numbers, tabular
 * figures come from the components' CSS. Missing values (null, undefined, NaN) read as an em dash.
 */

/** The tone a formatted value carries: `up` / `down` for signed changes, `muted` for missing. */
export type ValueTone = 'default' | 'up' | 'down' | 'muted';

/** How a value is shown. Every kind accepts `digits` (fraction digits) where it applies. */
export type ValueFormat =
  | { kind: 'text' }
  /** Grouped number: `11,427`, `1.49` (digits default 0). */
  | { kind: 'number'; digits?: number }
  /** A fraction shown as a percent: 0.721 -> `72.1%` (digits default 1). */
  | { kind: 'percent'; digits?: number }
  /** US dollars: `$333.69` (digits default 2). */
  | { kind: 'currency'; digits?: number }
  /** Compact US dollars: two decimals under 100 of a unit, none above: `$13.99B`, `$412M`, `$4.87T`. */
  | { kind: 'currency-compact' }
  /** Compact count: `11.4K`, `2.4M`. */
  | { kind: 'compact' }
  /** ISO date (`2026-10-02`) or Date: `short` = `2 Oct 2026`, `weekday` = `Fri 2 Oct`, `iso`. */
  | { kind: 'date'; style?: 'short' | 'weekday' | 'iso' }
  /**
   * A signed change with an up / down tone: `percent` (a fraction, +0.0124 -> `+1.24%`),
   * `points` (`+3.2 pts`) or `number` (`+1.20`). Zero has no tone.
   */
  | { kind: 'delta'; unit?: 'percent' | 'points' | 'number'; digits?: number };

export interface FormattedValue {
  text: string;
  tone: ValueTone;
}

/** The text shown for a missing value. */
export const MISSING = '—';
const MINUS = '−';

const numberFormats = new Map<string, Intl.NumberFormat>();
function numberFormat(key: string, options: Intl.NumberFormatOptions): Intl.NumberFormat {
  let found = numberFormats.get(key);
  if (!found) {
    found = new Intl.NumberFormat('en-US', options);
    numberFormats.set(key, found);
  }
  return found;
}

const fixed = (digits: number) =>
  numberFormat(`fixed-${digits}`, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });

/** Typographic minus (U+2212) instead of a hyphen, as in the mockups. */
const withMinus = (text: string): string => text.replace(/^-/, MINUS);

function isMissing(value: unknown): boolean {
  return (
    value === null ||
    value === undefined ||
    value === '' ||
    (typeof value === 'number' && Number.isNaN(value))
  );
}

function toDate(value: unknown): Date | undefined {
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? undefined : value;
  if (typeof value === 'string') {
    // A bare date is a calendar day, not an instant: read it as UTC midnight.
    const date = new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T00:00:00Z` : value);
    return Number.isNaN(date.getTime()) ? undefined : date;
  }
  if (typeof value === 'number') return new Date(value);
  return undefined;
}

function formatDate(value: unknown, style: 'short' | 'weekday' | 'iso'): string {
  const date = toDate(value);
  if (!date) return MISSING;
  if (style === 'iso') return date.toISOString().slice(0, 10);
  const options: Intl.DateTimeFormatOptions =
    style === 'weekday'
      ? { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' }
      : { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' };
  return new Intl.DateTimeFormat('en-GB', options).format(date).replace(',', '');
}

function formatDelta(
  value: number,
  unit: 'percent' | 'points' | 'number',
  digits: number | undefined,
): FormattedValue {
  const scaled = unit === 'percent' ? value * 100 : value;
  const places = digits ?? (unit === 'points' ? 1 : 2);
  const magnitude = fixed(places).format(Math.abs(scaled));
  const zero = Number(magnitude.replace(/,/g, '')) === 0;
  const sign = zero ? '' : scaled > 0 ? '+' : MINUS;
  const suffix = unit === 'percent' ? '%' : unit === 'points' ? ' pts' : '';
  return {
    text: `${sign}${magnitude}${suffix}`,
    tone: zero ? 'default' : scaled > 0 ? 'up' : 'down',
  };
}

/** Formats one value. Non-numeric input to a numeric format is shown as text. */
export function formatValue(
  value: unknown,
  format: ValueFormat = { kind: 'text' },
): FormattedValue {
  if (isMissing(value)) return { text: MISSING, tone: 'muted' };
  if (format.kind === 'date')
    return { text: formatDate(value, format.style ?? 'short'), tone: 'default' };
  if (format.kind === 'text' || typeof value !== 'number') {
    return { text: String(value), tone: 'default' };
  }
  switch (format.kind) {
    case 'number':
      return { text: withMinus(fixed(format.digits ?? 0).format(value)), tone: 'default' };
    case 'percent':
      return {
        text: `${withMinus(fixed(format.digits ?? 1).format(value * 100))}%`,
        tone: 'default',
      };
    case 'currency': {
      const text = fixed(format.digits ?? 2).format(Math.abs(value));
      return { text: `${value < 0 ? MINUS : ''}$${text}`, tone: 'default' };
    }
    case 'currency-compact': {
      // Two decimals below 100 of a unit ($13.99B, $1.59B), none above ($412M).
      const two = numberFormat('compact-2', { notation: 'compact', maximumFractionDigits: 2 });
      const none = numberFormat('compact-0', { notation: 'compact', maximumFractionDigits: 0 });
      const abs = Math.abs(value);
      const first = two.format(abs);
      const text = Number.parseFloat(first) >= 100 ? none.format(abs) : first;
      return { text: `${value < 0 ? MINUS : ''}$${text}`, tone: 'default' };
    }
    case 'compact':
      return {
        text: withMinus(
          numberFormat('compact-3', { notation: 'compact', maximumSignificantDigits: 3 }).format(
            value,
          ),
        ),
        tone: 'default',
      };
    case 'delta':
      return formatDelta(value, format.unit ?? 'percent', format.digits);
  }
}

/** True when a format is numeric (right-aligned, tabular figures). */
export function isNumericFormat(format: ValueFormat | undefined): boolean {
  return format !== undefined && format.kind !== 'text' && format.kind !== 'date';
}
