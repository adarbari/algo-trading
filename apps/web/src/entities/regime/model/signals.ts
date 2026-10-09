/**
 * The signal timing around a reference market fall (`Episode.signals`) and its mapping to the
 * design system's `Timeline`: one overview row per episode (a marker where each signal first
 * flagged) and the per-signal rows of one episode (a bar from flagged to cleared, the gate
 * apart). Days are the server's, exchange sessions from the episode's peak (negative: before it);
 * `state` is the server's verdict (LED, LATE, NEVER_FIRED, UNKNOWN) and is only worded and
 * toned here, never inferred from the days.
 */
import type { TimelineMarker, TimelineRow, TimelineSpan } from '@algotrade/ui';

import { unknownText } from '@/entities/availability';
import type { gqlTypes } from '@/shared/api';

import type { RegimeEpisode, RegimeIndicator, RegimeUnknown } from './regime';

export type SignalKind = gqlTypes.SignalKind;
export type SignalState = gqlTypes.SignalState;

/** One signal (an indicator card, or the screener gate) around one episode. */
export interface SignalTiming {
  /** The card key, or `gate`. */
  indicator: string;
  kind: SignalKind;
  state: SignalState;
  flaggedDay: number | null;
  clearedDay: number | null;
  flaggedDayFromTrough: number | null;
  firstKnownDay: number | null;
  neverFired: boolean;
  /** Set exactly when `state` is UNKNOWN. */
  unknownReason: RegimeUnknown | null;
}

/** The screener gate and every indicator around one episode, as the session knew it. */
export interface EpisodeSignals {
  gate: SignalTiming;
  indicators: readonly SignalTiming[];
}

type Tone = TimelineMarker['tone'];

/** Fast and slow signs differ by colour, the gate by colour and by its diamond marker. */
const KIND_TONE: Record<SignalKind, Tone> = { FAST: 's1', SLOW: 's2', GATE: 'neutral' };

/** The key of the timeline's signal kinds (the page's legend). */
export const SIGNAL_KEY: readonly { label: string; tone: Tone }[] = [
  { label: 'Fast signs', tone: KIND_TONE.FAST },
  { label: 'Slow signs', tone: KIND_TONE.SLOW },
  { label: 'Screener gate (diamond)', tone: KIND_TONE.GATE },
];

/** The signal's plain name: the card's, or the gate's. */
export function signalName(timing: SignalTiming, indicators: readonly RegimeIndicator[]): string {
  if (timing.kind === 'GATE') return 'Screener gate';
  return (
    indicators.find((indicator) => indicator.key === timing.indicator)?.plainName ??
    timing.indicator.replace(/_/g, ' ')
  );
}

/** The state in words, for the states that are not a plain lead (none for LED). */
export function signalNote(timing: SignalTiming): string | undefined {
  switch (timing.state) {
    case 'LED':
      return undefined;
    case 'LATE':
      return 'Late';
    case 'NEVER_FIRED':
      return 'Never fired';
    case 'UNKNOWN':
      return `Unknown: ${unknownText(timing.unknownReason)}`;
    default: {
      const unreachable: never = timing.state;
      return unreachable;
    }
  }
}

const marker = (timing: SignalTiming, name: string, day: number): TimelineMarker => ({
  id: timing.indicator,
  at: day,
  tone: KIND_TONE[timing.kind],
  ...(timing.kind === 'GATE' ? { shape: 'diamond' as const } : {}),
  ...(timing.state === 'LATE' ? { hollow: true } : {}),
  label: `${name} flagged`,
});

/** The signals of one episode, the gate first. */
function allTimings(signals: EpisodeSignals): readonly SignalTiming[] {
  return [signals.gate, ...signals.indicators];
}

/** One overview row: the episode's name and a marker where each signal first flagged. */
export function overviewRow(
  episode: RegimeEpisode,
  signals: EpisodeSignals | null,
  indicators: readonly RegimeIndicator[],
): TimelineRow {
  const markers =
    signals === null
      ? []
      : allTimings(signals).flatMap((timing) =>
          timing.flaggedDay === null
            ? []
            : [marker(timing, signalName(timing, indicators), timing.flaggedDay)],
        );
  return { id: episode.key, label: episode.name, markers };
}

/** The rows of one episode: a bar per signal from flagged to cleared (open while still on), the gate first. */
export function detailRows(
  signals: EpisodeSignals,
  indicators: readonly RegimeIndicator[],
): TimelineRow[] {
  return allTimings(signals).map((timing) => {
    const name = signalName(timing, indicators);
    const note = signalNote(timing);
    const spans: TimelineSpan[] =
      timing.flaggedDay === null
        ? []
        : [
            {
              id: timing.indicator,
              from: timing.flaggedDay,
              to: timing.clearedDay,
              tone: KIND_TONE[timing.kind],
              ...(timing.state === 'LATE' ? { variant: 'outline' as const } : {}),
              ...(timing.firstKnownDay === null ? {} : { openStart: true }),
              label: `${name} on`,
            },
          ];
    return {
      id: timing.indicator,
      label: name,
      ...(note === undefined ? {} : { note }),
      spans,
      markers:
        timing.kind === 'GATE' && timing.flaggedDay !== null
          ? [marker(timing, name, timing.flaggedDay)]
          : [],
    };
  });
}
