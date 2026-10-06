/**
 * The crosshair read-out: the day, each series' value (tabular, through formatValue), the volume
 * and that day's events, in a small bordered box beside the crosshair (flipped to its left on the
 * right half). Visual only: the same numbers are in the summary and the table view.
 */
import { formatValue, type ValueFormat } from '../../format';
import { EVENT_KINDS, type ChartEvent, type ChartLane, type PreparedChart } from './chartData';
import styles from './Chart.module.css';
import type { CrosshairInfo } from './engine';

export interface ChartTooltipProps {
  at: CrosshairInfo;
  chart: PreparedChart;
  /** Value of each series by id, then by day. */
  values: ReadonlyMap<string, ReadonlyMap<string, number>>;
  volume: ReadonlyMap<string, number>;
  events: ReadonlyMap<string, readonly ChartEvent[]>;
  /** The lanes: the segment of each that covers the day is read out under the values. */
  lanes: readonly ChartLane[];
  format: ValueFormat;
  /** Plot width in px: past the middle the box flips to the crosshair's left. */
  width: number;
}

export function ChartTooltip({
  at,
  chart,
  values,
  volume,
  events,
  lanes,
  format,
  width,
}: ChartTooltipProps) {
  const day = events.get(at.time) ?? [];
  const vol = volume.get(at.time);
  return (
    <div
      className={styles.tooltip}
      data-side={at.x > width / 2 ? 'start' : 'end'}
      style={{ insetInlineStart: `${String(Math.round(at.x))}px` }}
      aria-hidden="true"
    >
      <div className={styles.tooltipDate}>
        {formatValue(at.time, { kind: 'date', style: 'short' }).text}
      </div>
      {chart.series.map((s) => (
        <div key={s.id} className={styles.tooltipRow}>
          <span className={styles.tooltipSwatch} data-tone={s.tone} />
          <span className={styles.tooltipLabel}>{s.label}</span>
          <span className={styles.tooltipValue}>
            {formatValue(values.get(s.id)?.get(at.time), format).text}
          </span>
        </div>
      ))}
      {vol !== undefined && (
        <div className={styles.tooltipRow}>
          <span className={styles.tooltipLabel}>Volume</span>
          <span className={styles.tooltipValue}>{formatValue(vol, { kind: 'compact' }).text}</span>
        </div>
      )}
      {lanes.flatMap((lane) => {
        const segment = lane.segments.find((g) => at.time >= g.start && at.time <= g.end);
        return segment?.label === undefined
          ? []
          : [
              <div key={lane.id} className={styles.tooltipRow}>
                <span className={styles.tooltipLabel}>{lane.label}</span>
                <span className={styles.tooltipValue}>{segment.label}</span>
              </div>,
            ];
      })}
      {day.map((e) => (
        <div key={`${e.kind}-${e.time}`} className={styles.tooltipEvent}>
          {EVENT_KINDS[e.kind].letter} {EVENT_KINDS[e.kind].label}
          {e.detail ? ` · ${e.detail}` : ''}
        </div>
      ))}
    </div>
  );
}
