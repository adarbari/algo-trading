/**
 * ViewChips: a row of saved views of a table or list (presets such as "Top today", a user's own
 * views), exactly one in use. Each view is a toggle chip (pressed when in use) and the row wraps,
 * so it never overflows a phone. Pass the views and the one in use; the caller owns what a view
 * means. For two to four short mutually exclusive options in a toolbar use SegmentedControl.
 */
import { Stack } from '../../primitives/Stack';
import { Chip } from '../Chip';
import styles from './ViewChips.module.css';

export interface ViewOption<V extends string = string> {
  value: V;
  label: string;
}

export interface ViewChipsProps<V extends string = string> {
  /** The views, in display order. */
  views: readonly ViewOption<V>[];
  /** The view in use. */
  value: V;
  onValueChange: (value: V) => void;
}

export function ViewChips<V extends string = string>({
  views,
  value,
  onValueChange,
}: ViewChipsProps<V>) {
  return (
    <div className={styles.root}>
      <Stack direction="row" gap={1} align="center" wrap>
        {views.map((view) => (
          <Chip
            key={view.value}
            label={view.label}
            selected={view.value === value}
            onSelectedChange={() => {
              onValueChange(view.value);
            }}
          />
        ))}
      </Stack>
    </div>
  );
}
