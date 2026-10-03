/**
 * KeyValue: a definition list for detail panels: a label column and a value column (`<dl>`),
 * values tabular. Values are text or formatted with a ValueFormat (`$13.99B`, `+1.24%` with its
 * up / down tone); an optional hint (a feature id, a unit, a rule) sits under the label. Loading
 * shows placeholder values, an empty list shows the empty message.
 */
import type { ReactNode } from 'react';

import { formatValue, type ValueFormat } from '../../format';
import styles from './KeyValue.module.css';

export interface KeyValueItem {
  /** Stable key (defaults to the label). */
  id?: string;
  label: ReactNode;
  /** The value: a node, or a raw value formatted with `format`. */
  value: ReactNode;
  /** Formats a raw (number / string / date) value; numeric formats right-align in `columns`. */
  format?: ValueFormat;
  /** Secondary line under the label (feature id, unit, rule). */
  hint?: ReactNode;
  /** Set the value in the monospace face (symbols, ids). */
  mono?: boolean;
}

export interface KeyValueProps {
  items: readonly KeyValueItem[];
  /** `columns` (label beside value, the default) or `stacked` (label above value). */
  layout?: 'columns' | 'stacked';
  /** Align values to the end of the value column (numbers). */
  alignValues?: 'start' | 'end';
  /** Show placeholders instead of values. */
  loading?: boolean;
  /** Shown when there are no items. */
  emptyMessage?: ReactNode;
  /** Accessible name for the list. */
  label?: string;
}

function renderValue(item: KeyValueItem): { node: ReactNode; tone: string } {
  if (
    item.format &&
    (typeof item.value === 'number' ||
      typeof item.value === 'string' ||
      item.value === null ||
      item.value === undefined)
  ) {
    const formatted = formatValue(item.value, item.format);
    return { node: formatted.text, tone: formatted.tone };
  }
  return { node: item.value, tone: 'default' };
}

export function KeyValue({
  items,
  layout = 'columns',
  alignValues = 'start',
  loading = false,
  emptyMessage = 'Nothing to show',
  label,
}: KeyValueProps) {
  if (!loading && items.length === 0) {
    return <p className={styles.empty}>{emptyMessage}</p>;
  }
  return (
    <dl
      className={styles.list}
      data-layout={layout}
      data-align={alignValues}
      aria-label={label}
      aria-busy={loading || undefined}
    >
      {items.map((item, index) => {
        const { node, tone } = renderValue(item);
        return (
          <div
            key={item.id ?? (typeof item.label === 'string' ? item.label : index)}
            className={styles.row}
          >
            <dt className={styles.term}>
              <span className={styles.label}>{item.label}</span>
              {item.hint !== undefined && <span className={styles.hint}>{item.hint}</span>}
            </dt>
            <dd className={styles.value} data-tone={tone} data-mono={item.mono || undefined}>
              {loading ? <span className={styles.placeholder} aria-hidden="true" /> : node}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}
