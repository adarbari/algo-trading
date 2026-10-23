/**
 * ZeroResults: what a filtered list shows when nothing matches: an `EmptyState` with the best
 * ways back as recovery chips ("Switch off Liquidity gives 31": one chip per filter, with the
 * row count the server computed) and a clear-all button. Picking a chip reports its id. The
 * chips are plain action buttons in a wrapping row (not `ActionGroup`, which collapses to icons
 * on a phone: a chip's number must stay readable). All words are props.
 */
import type { ReactNode } from 'react';

import { formatValue } from '../../format';
import { Stack } from '../../primitives/Stack';
import { Button } from '../Button';
import { Chip } from '../Chip';
import { EmptyState } from '../EmptyState';
import styles from './ZeroResults.module.css';

export interface RecoveryItem {
  id: string;
  /** What the chip does ("Switch off Liquidity"). */
  label: string;
  /** Rows the list would show after it (server-counted). */
  gives: number;
}

export interface ZeroResultsProps {
  /** What is missing ("No ideas match all 3 filters"). */
  title: ReactNode;
  /** The loosening chips, best first. */
  items: readonly RecoveryItem[];
  /** A chip was picked. */
  onPick: (id: string) => void;
  /** Remove every filter. */
  onClearAll: () => void;
  /** The word between a chip's label and its count (default "gives"). */
  givesLabel?: string;
  /** Text of the clear button (default "Clear all"). */
  clearLabel?: string;
}

export function ZeroResults({
  title,
  items,
  onPick,
  onClearAll,
  givesLabel = 'gives',
  clearLabel = 'Clear all',
}: ZeroResultsProps) {
  return (
    <div className={styles.root}>
      <EmptyState
        icon="search"
        title={title}
        action={
          <Stack direction="row" gap={1} align="center" wrap>
            {items.map((item) => (
              <Chip
                key={item.id}
                label={`${item.label} ${givesLabel} ${formatValue(item.gives, { kind: 'number' }).text}`}
                onClick={() => {
                  onPick(item.id);
                }}
              />
            ))}
            <Button size="sm" variant="ghost" onClick={onClearAll}>
              {clearLabel}
            </Button>
          </Stack>
        }
      />
    </div>
  );
}
