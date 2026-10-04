/** A narrow miss in words. Pure. */
import { formatNumber } from '@/shared/lib';
import type { NarrowMiss } from '@/entities/screen';

/** "AAPL  0.48 vs 0.5, short by 0.02". */
export function missText(miss: NarrowMiss, symbol: string | null): string {
  const value = typeof miss.value === 'number' ? formatNumber(miss.value, 3) : String(miss.value);
  const threshold = miss.threshold === null ? '' : ` vs ${formatNumber(miss.threshold, 3)}`;
  const distance = miss.distance === null ? '' : `, short by ${formatNumber(miss.distance, 3)}`;
  return `${symbol ?? miss.instrument_id}  ${value}${threshold}${distance}`;
}
