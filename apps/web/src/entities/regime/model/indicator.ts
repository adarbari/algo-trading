/**
 * What an indicator card says about itself beyond the verdict (RG7): the meter's threshold and
 * its words, the sources in reading order and the provenance line under them. The numbers, the
 * range, the direction, the sources and their dates are the server's; this file only chooses
 * the words, in the plain order a reader meets them.
 */
import type { ScoreDirection, ScoreThreshold, SourceLineItem } from '@algotrade/ui';
import { formatValue, type ValueFormat } from '@algotrade/ui';

import { valueFormat } from '@/entities/feature';

import type { IndicatorSource, RegimeIndicator } from './regime';

export const NOT_USED_TODAY = 'not used today';

/**
 * How an indicator's value, range, threshold and history read: the catalogue `format` (NUMBER
 * when it is not in the catalogue yet), with whole numbers on a wide range (basis points, index
 * levels) and two decimals otherwise.
 */
export function indicatorFormat(indicator: RegimeIndicator): ValueFormat {
  const format = valueFormat({ format: indicator.format ?? 'NUMBER', dtype: 'float64' });
  const wide = indicator.range.max - indicator.range.min >= 100;
  return format.kind === 'number' && wide ? { kind: 'number', digits: 0 } : format;
}

/** The meter's direction for a card (no rule in code: the high side is the risk). */
export function meterDirection(indicator: RegimeIndicator): ScoreDirection {
  return indicator.direction === 'LOWER_IS_RISK' ? 'lower-is-risk' : 'higher-is-risk';
}

/** The meter's one threshold, the point where the indicator is on (none when there is no rule). */
export function meterThresholds(indicator: RegimeIndicator): ScoreThreshold[] {
  return indicator.threshold === null
    ? []
    : [{ at: indicator.threshold, label: 'on', tone: 'warning' }];
}

/** "On when above 0.5" / "On when below 0.5": the rule in words, under the meter. */
export function onWhenLine(indicator: RegimeIndicator, format: ValueFormat): string | undefined {
  if (indicator.threshold === null) return undefined;
  const side = meterDirection(indicator) === 'lower-is-risk' ? 'below' : 'above';
  return `On when ${side} ${formatValue(indicator.threshold, format).text}`;
}

/**
 * The source line's items: the source that fed today's value first, the others after it marked
 * "not used today". A source with no page of its own has no link, so the line names it in
 * `unlinked` instead.
 */
export function sourceItems(indicator: RegimeIndicator): {
  linked: SourceLineItem[];
  unlinked: string[];
} {
  const ordered = [...indicator.sources].sort((a, b) => Number(b.active) - Number(a.active));
  const linked: SourceLineItem[] = [];
  const unlinked: string[] = [];
  for (const source of ordered) {
    const cadence = source.active ? source.cadence : `${source.cadence}, ${NOT_USED_TODAY}`;
    if (source.url === null) unlinked.push(`${source.label} · ${cadence}`);
    else linked.push({ label: source.label, cadence, url: source.url });
  }
  return { linked, unlinked };
}

const day = (iso: string): string => formatValue(iso, { kind: 'date', style: 'short' }).text;

/**
 * The provenance of one source: its latest observation and the day it was public, and, for a
 * revised series, that values before the first stored vintage are today's revised figures.
 * Null when nothing is known about the source (an unstored one).
 */
export function provenanceLine(source: IndicatorSource): string | null {
  if (!source.active || source.lastObservation === null) return null;
  const released = source.vintageDate === null ? '' : `, released ${day(source.vintageDate)}`;
  const revised =
    source.firstVintage === null
      ? ''
      : `; before ${day(source.firstVintage)} values are today's revised figures`;
  return `${source.label}: last observation ${day(source.lastObservation)}${released}${revised}`;
}
