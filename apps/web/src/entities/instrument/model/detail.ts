/**
 * An instrument's detail as Explore shows it: the display name and every catalogue field's
 * value for the session (reference facts, company details, rollup and expression features).
 */
import type { components } from '@/shared/api';

export type InstrumentDetail = components['schemas']['InstrumentDetail'];
export type FeatureSeries = components['schemas']['FeatureSeries'];

const INSTRUMENT = 'instrument.';

/** The value of catalogue field `name` for this instrument (undefined: not in the detail). */
export function fieldValue(detail: InstrumentDetail, name: string): unknown {
  if (name.startsWith(INSTRUMENT)) {
    const column = name.slice(INSTRUMENT.length);
    if (column in detail.reference) return detail.reference[column];
    return detail.company?.[column];
  }
  return detail.features[name];
}

/** The company's name, else the listing's. */
export function displayName(detail: InstrumentDetail): string {
  const company = detail.company?.['name'];
  const listing = detail.reference['name'];
  if (typeof company === 'string' && company) return company;
  return typeof listing === 'string' ? listing : '';
}

/** One feature's values over the series' sessions, oldest first (non-numbers are gaps). */
export function historyOf(series: FeatureSeries, name: string): (number | null)[] {
  return series.items.map((item) => {
    const value = item[name];
    return typeof value === 'number' && Number.isFinite(value) ? value : null;
  });
}
