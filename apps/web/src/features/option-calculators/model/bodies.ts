/**
 * What a trader typed into an option calculator, as the request body it becomes, or null while the
 * form is not complete (so the button stays off). Nothing is derived: figures pass through as typed.
 */
import type { components } from '@/shared/api';

export type RollBody = components['schemas']['RollBody'];
export type CallsBody = components['schemas']['CallsBody'];

/** The roll form as typed; empty fields are null. */
export interface RollForm {
  strike: number | null;
  /** The expiry day (`YYYY-MM-DD`) picked from the listed expiries; empty until picked. */
  expiry: string;
  soldAt: number | null;
}

/** The calls form as typed. */
export interface CallsForm {
  shares: number | null;
  price: number | null;
}

/** The roll request for a put the trader sold, or null until the strike and the expiry are given. */
export function rollBody(
  symbol: string,
  form: RollForm,
  options: { includeDebits: boolean; sameDelta: boolean },
): RollBody | null {
  if (form.strike === null || form.strike <= 0 || form.expiry === '') return null;
  return {
    key: symbol,
    right: 'put',
    strike: form.strike,
    expiry: form.expiry,
    sold_at: form.soldAt,
    include_debits: options.includeDebits,
    same_delta: options.sameDelta,
  };
}

/** The calls request, or null until whole shares and a price are given. */
export function callsBody(symbol: string, form: CallsForm): CallsBody | null {
  const { shares, price } = form;
  if (shares === null || !Number.isInteger(shares) || shares <= 0 || shares > 10_000_000)
    return null;
  if (price === null || price <= 0) return null;
  return { key: symbol, shares, price };
}
