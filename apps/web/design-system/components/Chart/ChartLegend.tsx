/**
 * The chart's key: one line swatch per series (Legend) and, when events are drawn, one marker
 * glyph per event kind with its letter and name, the same shapes the canvas draws (circle,
 * square, arrow), so neither series nor events rely on colour alone.
 */
import { Legend } from '../Legend';
import { EVENT_KINDS, type ChartEventKind, type PreparedChart } from './chartData';
import styles from './Chart.module.css';

function Glyph({ kind }: { kind: ChartEventKind }) {
  return (
    <svg className={styles.glyph} viewBox="0 0 12 12" aria-hidden="true" focusable="false">
      {kind === 'dividend' && <circle cx="6" cy="6" r="4" />}
      {kind === 'split' && <rect x="2" y="2" width="8" height="8" />}
      {kind === 'earnings' && <path d="M6 1.5 10.5 9H1.5z" />}
    </svg>
  );
}

export function ChartLegend({ chart }: { chart: PreparedChart }) {
  const kinds = (Object.keys(EVENT_KINDS) as ChartEventKind[]).filter((kind) =>
    chart.events.some((e) => e.kind === kind),
  );
  return (
    <div className={styles.legend}>
      <Legend
        swatch="line"
        size="xs"
        label="Series"
        items={chart.series.map((s) => ({ id: s.id, label: s.label, tone: s.tone }))}
      />
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
