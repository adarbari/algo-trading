/**
 * The `f` search parameter's grammar: filters joined by `;`, each `[!]id:body`, `!` meaning
 * switched off. A body is pick values (`QUALIFIED,WATCH`), a range (`30..70`, `..14`, `5..`) or
 * a window (`..5s` sessions, `..14d` days). A `,` `;` `:` `%` in an id or value is
 * percent-encoded (so is a `.` when a value holds `..`, and a leading `!`). Malformed entries
 * are dropped, never thrown; the first entry of a repeated id wins; order is kept.
 */
import type { FilterState, FilterUnit } from './state';

const UNIT_SUFFIX: Record<FilterUnit, string> = { days: 'd', sessions: 's' };

function escape(text: string): string {
  let out = text.replace(/[%,;:]/g, (c) => `%${c.charCodeAt(0).toString(16).toUpperCase()}`);
  if (out.includes('..')) out = out.replaceAll('.', '%2E');
  if (out.startsWith('!')) out = `%21${out.slice(1)}`;
  return out;
}

function unescape(text: string): string | undefined {
  try {
    return decodeURIComponent(text);
  } catch {
    return undefined;
  }
}

function encodeBody(filter: FilterState): string {
  if (filter.within) {
    return `..${String(filter.within.amount)}${UNIT_SUFFIX[filter.within.unit]}`;
  }
  if (filter.min !== undefined || filter.max !== undefined) {
    const lo = filter.min === undefined || !Number.isFinite(filter.min) ? '' : String(filter.min);
    const hi = filter.max === undefined || !Number.isFinite(filter.max) ? '' : String(filter.max);
    return `${lo}..${hi}`;
  }
  return (filter.values ?? []).map(escape).join(',');
}

/** The `f` value for a filter list; the empty string when there is none. */
export function encodeFilters(filters: readonly FilterState[]): string {
  const seen = new Set<string>();
  const parts: string[] = [];
  for (const filter of filters) {
    if (!filter.id || seen.has(filter.id)) continue;
    seen.add(filter.id);
    parts.push(`${filter.active ? '' : '!'}${escape(filter.id)}:${encodeBody(filter)}`);
  }
  return parts.join(';');
}

const NUMBER = /^-?\d+(\.\d+)?(e[+-]?\d+)?$/;

function bound(text: string): number | undefined | null {
  if (text === '') return undefined;
  return NUMBER.test(text) ? Number(text) : null;
}

function decodeBody(body: string): Omit<FilterState, 'id' | 'active'> | null {
  const windowMatch = /^\.\.(\d+)([ds])$/.exec(body);
  if (windowMatch) {
    const unit: FilterUnit = windowMatch[2] === 's' ? 'sessions' : 'days';
    return { within: { amount: Number(windowMatch[1]), unit } };
  }
  const at = body.indexOf('..');
  if (at >= 0 && !body.includes(',')) {
    const lo = bound(body.slice(0, at));
    const hi = bound(body.slice(at + 2));
    if (lo === null || hi === null || (lo === undefined && hi === undefined)) return null;
    return {
      ...(lo === undefined ? {} : { min: lo }),
      ...(hi === undefined ? {} : { max: hi }),
    };
  }
  const values: string[] = [];
  for (const raw of body.split(',')) {
    if (raw === '') continue;
    const value = unescape(raw);
    if (value === undefined) return null;
    values.push(value);
  }
  return values.length > 0 ? { values } : {};
}

/** The filter list an `f` value holds (empty for undefined or garbage). */
export function decodeFilters(f: string | undefined): FilterState[] {
  if (!f) return [];
  const seen = new Set<string>();
  const out: FilterState[] = [];
  for (const entry of f.split(';')) {
    const colon = entry.indexOf(':');
    if (colon < 0) continue;
    const head = entry.slice(0, colon);
    const active = !head.startsWith('!');
    const id = unescape(active ? head : head.slice(1));
    const body = decodeBody(entry.slice(colon + 1));
    if (!id || !body || seen.has(id)) continue;
    seen.add(id);
    out.push({ id, ...body, active });
  }
  return out;
}
