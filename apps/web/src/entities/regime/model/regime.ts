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
  /** The catalogue field the history chart reads (`market.regime@v3.macro_risk`). */
  feature: string;
  /** The field of the share of the score's weight known (null: the score has none). */
  coverageFeature: string | null;
  /** At or above it the score is high for the label (null: context only). */
  threshold: number | null;
}

/** A piece of a sentence, a link when `url` is set (`IndicatorSource.terms` is plain text). */
export interface TextPart {
  text: string;
  url: string | null;
}

/** Where an indicator's value comes from (one series or table), with its provenance. */
export interface IndicatorSource {
  label: string;
  series: string | null;
  /** "weekly", "daily, after the close". */
  cadence: string;
  releaseLagDays: number | null;
  url: string | null;
  licence: string;
  terms: string | null;
  /** The latest observation the session knew, and the day it became public. */
  lastObservation: string | null;
  vintageDate: string | null;
  vintageKind: string | null;
  /** The earliest ALFRED vintage the session knew: before it the history is revised figures. */
  firstVintage: string | null;
  /** It fed today's value (false: the source a per-session switch did not choose). */
  active: boolean;
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
  /** The catalogue field of the value (the history chart's line). */
  feature: string;
  /** The catalogue field of the verdict (`<card>_on`: a flag; the history chart's lane). */
  verdictFeature: string;
  /** The meter's display range, in the value's stored unit. */
  range: { min: number; max: number };
  /** Where the indicator turns on (null: no rule in code), and which side is the risk. */
  threshold: number | null;
  direction: gqlTypes.RiskDirection | null;
  /** How the value is calculated, as linked parts. */
  how: readonly TextPart[];
  sources: readonly IndicatorSource[];
}

/**
 * One reference market drawdown (`Query.regime.episodes`), known as of the session. `recovered`
 * is null until the session has seen the S&P 500 regain its peak.
 */
export interface RegimeEpisode {
  /** The `episodes.toml` key and the suffix of the `episode_behaviour@v1` feature names. */
  key: string;
  /** "Tariff shock, spring 2025". */
  name: string;
  kind: string;
  peak: string;
  trough: string;
  recovered: string | null;
  spxDrawdown: number;
  nasdaqDrawdown: number;
  recession: boolean;
  nberStart: string | null;
  nberEnd: string | null;
  cause: string;
  notes: string;
  knownFrom: string;
}

/** One NBER recession as the session knew it (`end` null: not yet dated over). */
export interface Recession {
  start: string;
  end: string | null;
  announcedStart: string | null;
  announcedEnd: string | null;
}

/** The plain name of an episode key (an unnamed key reads as itself, spaced). */
export function episodeName(episodes: readonly RegimeEpisode[], key: string): string {
  return episodes.find((episode) => episode.key === key)?.name ?? key.replace(/_/g, ' ');
}

/**
 * The stored regime label's field: the regime group names it beside its scores
 * (`market.regime@v3.label` next to `market.regime@v3.macro_risk`), so the history reads it
 * from the group the scores came from.
 */
export function regimeLabelFeature(regime: Regime): string {
  return regime.scores.macroRisk.feature.replace(/\.[^.]*$/, '.label');
}

/** A screener of the caller and the labels its picks are PAUSED in (calmest first). */
export interface ScreenerGate {
  screenerId: string;
  name: string;
  /** Its `[regime]` gate is on; off, nothing is paused. */
  enabled: boolean;
  pauseIn: readonly RegimeLabel[];
}

/** The sizing rule in force for the caller (`Query.regime.sizing`). */
export interface RegimeSizing {
  /** The session's label, and the size new positions get in it (null: UNKNOWN). */
  label: RegimeLabel;
  multiplier: number | null;
  /** The gate is on; off, sizes are 100% and nothing pauses. */
  enabled: boolean;
  multipliers: readonly { label: RegimeLabel; multiplier: number }[];
  /** The size when the label is not stored (the gate fails closed: 0 by default). */
  unknownMultiplier: number;
  screeners: readonly ScreenerGate[];
}

export interface Regime {
  session: string;
  label: RegimeLabel;
  headline: string;
  scores: { macroRisk: RegimeScore; marketStress: RegimeScore; fragility: RegimeScore };
  indicators: readonly RegimeIndicator[];
  sizing: RegimeSizing;
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

const percent = (value: number): string => formatValue(value, { kind: 'percent', digits: 0 }).text;

/** "Storm", "Storm and Severe storm", "Clouds building, Storm and Severe storm". */
function labelList(labels: readonly RegimeLabel[]): string {
  const words = labels.map(plainLabel);
  const last = words.at(-1);
  return words.length < 2 || last === undefined
    ? words.join('')
    : `${words.slice(0, -1).join(', ')} and ${last}`;
}

/** The screeners that pause in some label, as sentences ("VRP scanner pauses in Storm"). */
function pauseSentences(sizing: RegimeSizing): string[] {
  return sizing.screeners
    .filter((s) => s.enabled && s.pauseIn.length > 0)
    .map((s) => `${s.name} pauses in ${labelList(s.pauseIn)}`);
}

/**
 * The sizing line under the headline: the size new positions get now (the multiplier of the
 * session's label; the unknown size while the regime is not computed; 100% with the gate off)
 * and which of the caller's screeners pause in which labels. Words only: every number and list
 * is the server's.
 */
export function sizingLine(regime: Regime): string {
  const { sizing } = regime;
  if (!sizing.enabled) return 'New positions at full size (the regime gate is off)';
  const size =
    sizing.label === 'UNKNOWN' || sizing.multiplier === null
      ? `New positions sized at ${percent(sizing.unknownMultiplier)} (regime not computed)`
      : `New positions sized at ${percent(sizing.multiplier)} in ${plainLabel(sizing.label)}`;
  return [size, ...pauseSentences(sizing)].join('; ');
}

/**
 * The Builder's one-line gate summary for screener `screenerId`: the labels its picks pause in
 * ("This screen pauses in Storm and Severe storm"), else "No regime gate" (also for a screen
 * the caller has not saved yet).
 */
export function gateLine(sizing: RegimeSizing, screenerId: string): string {
  const gate = sizing.screeners.find((s) => s.screenerId === screenerId);
  if (!gate?.enabled || gate.pauseIn.length === 0) return 'No regime gate';
  return `This screen pauses in ${labelList(gate.pauseIn)}`;
}

/**
 * One screener's gate in words: "Pauses in Storm", "Never pauses", or with its gate off
 * "Gate off" (naming the labels it is set to pause in, for when it is turned on).
 */
export function gatePauses(gate: ScreenerGate): string {
  if (!gate.enabled) {
    return gate.pauseIn.length === 0
      ? 'Gate off'
      : `Gate off (set to pause in ${labelList(gate.pauseIn)})`;
  }
  return gate.pauseIn.length === 0 ? 'Never pauses' : `Pauses in ${labelList(gate.pauseIn)}`;
}

const LABELS: readonly string[] = ['CALM', 'CAUTION', 'STRESS', 'CRISIS'];

/** A run's stored label (a string) as a label, or null when it is not one of the four. */
export function storedLabel(
  value: string | null | undefined,
): Exclude<RegimeLabel, 'UNKNOWN'> | null {
  return value !== null && value !== undefined && LABELS.includes(value)
    ? (value as Exclude<RegimeLabel, 'UNKNOWN'>)
    : null;
}
