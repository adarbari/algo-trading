/**
 * The chart's key: one line swatch per series (Legend) and, when events are drawn, one marker
 * glyph per event kind with its letter and name, the same shapes the canvas draws (circle,
 * square, up and down arrows), so neither series nor events rely on colour alone; and, with `bandKey`, one
 * tinted cell per distinct shaded band (hatched ones with a hatch swatch), and one per distinct
 * lane segment label (tone and label).
 */
import { Legend } from '../Legend';
import {
  EVENT_KINDS,
  type ChartBandTone,
  type ChartEventKind,
  type PreparedChart,
} from './chartData';
import styles from './Chart.module.css';

function Glyph({ kind }: { kind: ChartEventKind }) {
  return (
    <svg className={styles.glyph} viewBox="0 0 12 12" aria-hidden="true" focusable="false">
      {(kind === 'dividend' || kind === 'macro') && <circle cx="6" cy="6" r="4" />}
      {kind === 'split' && <rect x="2" y="2" width="8" height="8" />}
      {kind === 'earnings' && <path d="M6 1.5 10.5 9H1.5z" />}
      {kind === 'filing' && <path d="M6 10.5 1.5 3h9z" />}
    </svg>
  );
}

export function ChartLegend({ chart, bandKey }: { chart: PreparedChart; bandKey: boolean }) {
  const kinds = (Object.keys(EVENT_KINDS) as ChartEventKind[]).filter((kind) =>
    chart.events.some((e) => e.kind === kind),
  );
  const distinct = <T extends { tone: ChartBandTone; label: string }>(items: readonly T[]) =>
    items.filter((b, i) => items.findIndex((o) => o.label === b.label && o.tone === b.tone) === i);
  const bands = distinct([
    ...chart.bands.filter((b) => b.pattern !== 'hatch'),
    ...chart.valueBands,
  ]);
  const hatched = distinct(chart.bands.filter((b) => b.pattern === 'hatch'));
  const states = distinct(
    chart.lanes.flatMap((lane) =>
      lane.segments.flatMap((g) =>
        g.label === undefined ? [] : [{ tone: g.tone, label: g.label }],
      ),
    ),
  );
  return (
    <div className={styles.legend}>
      <Legend
        swatch="line"
        size="xs"
        label="Series"
        items={chart.series.map((s) => ({ id: s.id, label: s.label, tone: s.tone }))}
      />
      {bandKey && bands.length > 0 && (
        <Legend
          swatch="cell"
          size="xs"
          label="Shaded periods"
          items={bands.map((b) => ({ id: `${b.tone}-${b.label}`, label: b.label, tone: b.tone }))}
        />
      )}
      {bandKey && hatched.length > 0 && (
        <Legend
          swatch="hatch"
          size="xs"
          label="Hatched periods"
          items={hatched.map((b) => ({ id: `${b.tone}-${b.label}`, label: b.label, tone: b.tone }))}
        />
      )}
      {bandKey && states.length > 0 && (
        <Legend
          swatch="cell"
          size="xs"
          label="Lane states"
          items={states.map((b) => ({ id: `${b.tone}-${b.label}`, label: b.label, tone: b.tone }))}
        />
      )}
      {kinds.length > 0 && (
        <ul className={styles.events} aria-label="Event markers">
          {kinds.map((kind) => (
            <li key={kind} className={styles.event}>
              <Glyph kind={kind} />
              <span>
                {EVENT_KINDS[kind].letter} {EVENT_KINDS[kind].label}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
