/**
 * TickerTag: a ticker symbol in mono, keyed to its chart series (s1-s6: border and swatch in the
 * series colour) so a compare list, a chart legend and a side-by-side table read as one. The
 * symbol itself stays in the text colour: series colours meet 3:1 for graphics, not 4.5:1 for
 * text. Optionally removable ("Remove AAPL from compare").
 */
import type { Series } from '../../tokens';
import { IconButton } from '../IconButton';
import styles from './TickerTag.module.css';

export interface TickerTagProps {
  /** The ticker ("AAPL"). */
  symbol: string;
  /** The entity's series slot (assigned in fixed order, never re-ranked); none = neutral. */
  series?: Series;
  /** Full name on hover ("Apple Inc."). */
  name?: string;
  /** Adds a remove button named "Remove <symbol>" (plus `removeContext`). */
  onRemove?: () => void;
  /** Completes the remove button's name: "from compare" gives "Remove AAPL from compare". */
  removeContext?: string;
}

export function TickerTag({ symbol, series, name, onRemove, removeContext }: TickerTagProps) {
  return (
    <span
      className={styles.tag}
      data-series={series}
      data-removable={onRemove ? true : undefined}
      title={name}
    >
      {series && <span className={styles.swatch} aria-hidden="true" />}
      <span className={styles.symbol}>{symbol}</span>
      {onRemove && (
        <IconButton
          icon="close"
          size="sm"
          label={`Remove ${symbol}${removeContext ? ` ${removeContext}` : ''}`}
          onClick={onRemove}
        />
      )}
    </span>
  );
}
