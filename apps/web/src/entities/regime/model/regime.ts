/**
 * The market regime as the read model serves it (ADR 0047): the weather words, the tone of
 * each label, the shape of `Query.regime`, and the mapping of the label history to the `Chart`
 * `bands` prop. The browser derives nothing: the label, the sentence, the scores and each
 * indicator's verdict come from the server; this file only chooses words and tones for them.
 */
import {
  formatValue,
  type ChartBand,
  type IndicatorChange,
  type IndicatorStatus,
  type StatusTone,
} from '@algotrade/ui';

import type { gqlTypes } from '@/shared/api';

export type RegimeLabel = gqlTypes.RegimeLabel;

/** A value the server could not give for the session, with its reason. */
export interface RegimeUnknown {
  code: string;
  detail: string;
}

export interface RegimeScore {
  value: number | null;
  unknown: RegimeUnknown | null;
}

export interface RegimeIndicator {
  key: string;
  /** `slow` (macro, weekly) or `fast` (market, daily). */
  pace: string;
  plainName: string;
  technicalName: string;
  oneLiner: string;
  whyItMatters: string;
  whatOnMeans: string;
  before: readonly { episode: string; line: string }[];
  leadTime: string;
  falseAlarms: string;
  links: readonly { title: string; url: string }[];
  value: unknown;
  unknown: RegimeUnknown | null;
  format: gqlTypes.FeatureFormat | null;
  status: gqlTypes.IndicatorStatus;
  /** The verdict differs from five sessions ago (null: not stored). */
  changed: boolean | null;
}

export interface Regime {
  session: string;
  label: RegimeLabel;
  headline: string;
  scores: { macroRisk: RegimeScore; marketStress: RegimeScore; fragility: RegimeScore };
  indicators: readonly RegimeIndicator[];
  sizing: { label: RegimeLabel; multiplier: number | null };
  /** Why the regime is not computed (UNKNOWN), else null. */
  unknownReason: RegimeUnknown | null;
}

export interface RegimeBand {
  start: string;
  end: string;
  label: RegimeLabel;
}

/** The weather word of each label (CALM = "Clear" ... CRISIS = "Severe storm"). */
export function plainLabel(label: RegimeLabel): string {
  switch (label) {
    case 'CALM':
      return 'Clear';
    case 'CAUTION':
      return 'Clouds building';
    case 'STRESS':
      return 'Storm';
    case 'CRISIS':
      return 'Severe storm';
    case 'UNKNOWN':
      return 'Not computed';
    default: {
      const unreachable: never = label;
      return unreachable;
    }
  }
}

/** The tone of each label: the words are always shown, the tone only reinforces them. */
export function regimeTone(label: RegimeLabel): StatusTone {
  switch (label) {
    case 'CALM':
      return 'positive';
    case 'CAUTION':
      return 'warning';
    case 'STRESS':
    case 'CRISIS':
      return 'negative';
    case 'UNKNOWN':
      return 'neutral';
    default: {
      const unreachable: never = label;
      return unreachable;
    }
  }
}

/**
 * The label history as chart bands, oldest first: each band is tinted by its label's tone and
 * named by its weather word (the chart's key lists one entry per distinct word). An UNKNOWN
 * band renders nothing: no stored label is not a regime. `from` keeps only that label and the
 * worse ones (the price chart shades `STRESS` and `CRISIS`).
 */
export function toChartBands(
  bands: readonly RegimeBand[],
  from: Exclude<RegimeLabel, 'UNKNOWN'> = 'CALM',
): ChartBand[] {
  const order: readonly RegimeLabel[] = ['CALM', 'CAUTION', 'STRESS', 'CRISIS'];
  const floor = order.indexOf(from);
  return bands
    .filter((band) => order.indexOf(band.label) >= floor)
    .map((band) => ({
      start: band.start,
      end: band.end,
      tone: regimeTone(band.label),
      label: plainLabel(band.label),
    }));
}

/** An indicator's verdict as the row's status: ON (the warning is on), OFF, or no verdict. */
export function indicatorStatus(status: gqlTypes.IndicatorStatus): IndicatorStatus {
  switch (status) {
    case 'ON':
      return { tone: 'warning', label: 'On' };
    case 'OFF':
      return { tone: 'positive', label: 'Off' };
    case 'UNKNOWN':
      return { tone: 'neutral', label: 'Unknown' };
    default: {
      const unreachable: never = status;
      return unreachable;
    }
  }
}

/**
 * The row's change marker for an indicator whose verdict differs from five sessions ago: up
 * (turned on) or down (turned off), with the words a screen reader hears; none when it did not
 * change, or when it is not stored.
 */
export function indicatorChange(
  indicator: RegimeIndicator,
): { change: IndicatorChange; label: string } | undefined {
  if (indicator.changed !== true) return undefined;
  if (indicator.status === 'ON') return { change: 'up', label: 'Turned on this week' };
  if (indicator.status === 'OFF') return { change: 'down', label: 'Turned off this week' };
  return { change: 'new', label: 'Changed this week' };
}

/** The indicators whose verdict changed since five sessions ago. */
export function changedIndicators(regime: Regime): readonly RegimeIndicator[] {
  return regime.indicators.filter((indicator) => indicator.changed === true);
}

/** The indicators of one pace (`slow` macro or `fast` market), in the cards' order. */
export function indicatorsOfPace(
  regime: Regime,
  pace: 'slow' | 'fast',
): readonly RegimeIndicator[] {
  return regime.indicators.filter((indicator) => indicator.pace === pace);
}

/** One reading-list entry: a link and the indicators whose card cites it. */
export interface ReadingLink {
  title: string;
  url: string;
  /** Plain names of the indicators that cite it. */
  cards: readonly string[];
}

/** Every card's links, de-duplicated by address (the first title wins), in card order. */
export function readingList(regime: Regime): readonly ReadingLink[] {
  const byUrl = new Map<string, { title: string; cards: string[] }>();
  for (const indicator of regime.indicators) {
    for (const link of indicator.links) {
      const entry = byUrl.get(link.url) ?? { title: link.title, cards: [] };
      if (!entry.cards.includes(indicator.plainName)) entry.cards.push(indicator.plainName);
      byUrl.set(link.url, entry);
    }
  }
  return [...byUrl].map(([url, { title, cards }]) => ({ title, url, cards }));
}

/** The sizing line under the headline (RG4 gives real sizing; until then the site default). */
export function sizingLine(regime: Regime): string {
  const { label, multiplier } = regime.sizing;
  if (label === 'UNKNOWN' || multiplier === null) {
    return 'New positions sized at 100% (regime not computed)';
  }
  return `New positions sized at ${formatValue(multiplier, { kind: 'percent', digits: 0 }).text} (${plainLabel(label).toLowerCase()})`;
}
