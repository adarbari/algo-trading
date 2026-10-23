/**
 * FilterBar: a table's filter bar (search, quick toggle chips, the many-valued filters in
 * force, and a "more filters" panel) that uses a phone's space well. Wide, the search takes
 * the row, under it the quick chips, the active chips and a "+ Filter" popover with the
 * fields. Narrow (the bar's own width under `sm`), `sheet`: the search and one "Filters · N"
 * button share a row, the button opens a side sheet with the quick chips and the fields, and
 * the active chips scroll sideways under the row. Narrow, `scroll`: the search, then one row
 * that scrolls sideways ("+ Filter" first, then the quick and the active chips). The two
 * narrow forms are proposals; the owner picks one (ADR 0011).
 * ADR 0082 adds: `groups` (`FilterGroupButton`s) on the toolbar row beside the search and the
 * "More filters" trigger; below the chips a count line with `count` (an `aria-live=polite`
 * region; narrow with the sheet open it is repeated in the sheet's footer: "12 of 340") and `actions` (Clear all, Save view); and, narrow, the sheet's footer
 * button (`applyLabel` / `onApply`: "Show 12 results"). Without them the bar is as before.
 */
import { useState, type ReactNode } from 'react';

import { Stack } from '../../primitives/Stack';
import { useNarrow } from '../../responsive';
import { Button } from '../Button';
import { Drawer } from '../Drawer';
import { Popover } from '../Popover';
import styles from './FilterBar.module.css';

export interface FilterBarProps {
  /** The caller's `SearchInput`. */
  search: ReactNode;
  /** Toggle `Chip`s of the quick filters. */
  quick?: ReactNode;
  /** Removable `Chip`s of the many-valued filters in force (null: none). */
  active?: ReactNode;
  /** The fields of the many-valued filters (a `Field` + `Select` stack). */
  more?: ReactNode;
  /** Text of the wide "+ Filter" trigger (default "Filter"). */
  moreLabel?: string;
  /** How many filters are in force: shown on the narrow button as "Filters · 2". */
  activeCount?: number;
  /** The narrow form: `sheet` (default) or `scroll`. */
  narrow?: 'sheet' | 'scroll';
  /** Accessible name of the bar (default "Filters"). */
  label?: string;
  /** The narrow filters sheet starts open (a story's open state). */
  defaultOpen?: boolean;
  /** One `FilterGroupButton` per group, on the toolbar row beside the search. */
  groups?: ReactNode;
  /** Buttons at the end of the count line (Clear all, Save view). */
  actions?: ReactNode;
  /** The result count text ("12 of 340"), announced politely when it changes. */
  count?: string;
  /** Text of the narrow sheet's footer button ("Show 12 results"). */
  applyLabel?: string;
  /** Called when the footer button is pressed; the sheet closes after it. */
  onApply?: () => void;
}

export function FilterBar({
  search,
  quick,
  active,
  more,
  moreLabel = 'Filter',
  activeCount,
  narrow: narrowForm = 'sheet',
  label = 'Filters',
  defaultOpen = false,
  groups,
  actions,
  count,
  applyLabel,
  onApply,
}: FilterBarProps) {
  const [ref, isNarrow] = useNarrow('sm');
  const [open, setOpen] = useState(defaultOpen);
  const hasMore = more !== undefined && more !== null;
  const hasActive = active !== undefined && active !== null;
  const trigger = hasMore ? (
    <Popover
      label="More filters"
      trapFocus
      trigger={(props) => (
        <Button {...props} variant="dashed" size="sm" icon="plus">
          {moreLabel}
        </Button>
      )}
    >
      {more}
    </Popover>
  ) : null;

  let body: ReactNode;
  const hasGroups = groups !== undefined && groups !== null;
  if (!isNarrow && hasGroups) {
    body = (
      <Stack gap={2}>
        <Stack direction="row" gap={2} align="center" wrap>
          <div className={styles.grow}>{search}</div>
          {groups}
          {trigger}
        </Stack>
        {quick || hasActive ? (
          <Stack direction="row" gap={1} align="center" wrap>
            {quick}
            {active}
          </Stack>
        ) : null}
      </Stack>
    );
  } else if (!isNarrow) {
    body = (
      <Stack gap={2}>
        {search}
        <Stack direction="row" gap={1} align="center" wrap>
          {quick}
          {active}
          {trigger}
        </Stack>
      </Stack>
    );
  } else if (narrowForm === 'scroll') {
    body = (
      <Stack gap={2}>
        {search}
        <div className={styles.scrollRow}>
          {trigger}
          {quick}
          {active}
        </div>
      </Stack>
    );
  } else {
    const badge = activeCount !== undefined && activeCount > 0 ? ` · ${activeCount}` : '';
    body = (
      <Stack gap={2}>
        <Stack direction="row" gap={2} align="center">
          <div className={styles.grow}>{search}</div>
          <Button
            size="sm"
            icon="filter"
            aria-haspopup="dialog"
            onClick={() => {
              setOpen(true);
            }}
          >
            {`Filters${badge}`}
          </Button>
        </Stack>
        {hasActive ? <div className={styles.scrollRow}>{active}</div> : null}
        <Drawer
          open={open}
          onOpenChange={setOpen}
          title="Filters"
          side="end"
          size="sm"
          footer={
            applyLabel !== undefined || count !== undefined ? (
              <Stack gap={2}>
                {count !== undefined && (
                  <span className={styles.count} aria-live="polite" aria-atomic="true">
                    {count}
                  </span>
                )}
                {applyLabel !== undefined && (
                  <Button
                    variant="primary"
                    fullWidth
                    onClick={() => {
                      onApply?.();
                      setOpen(false);
                    }}
                  >
                    {applyLabel}
                  </Button>
                )}
              </Stack>
            ) : undefined
          }
        >
          <Stack gap={3}>
            <Stack direction="row" gap={1} align="center" wrap>
              {quick}
            </Stack>
            {hasGroups ? (
              <Stack direction="row" gap={1} align="center" wrap>
                {groups}
              </Stack>
            ) : null}
            {more}
          </Stack>
        </Drawer>
      </Stack>
    );
  }
  const hasCount = count !== undefined || (actions !== undefined && actions !== null);
  return (
    <div ref={ref} className={styles.root} role="group" aria-label={label}>
      <Stack gap={2}>
        {body}
        {hasCount ? (
          <Stack direction="row" gap={2} align="center" justify="between" wrap>
            <span
              className={styles.count}
              aria-live={isNarrow && open ? undefined : 'polite'}
              aria-hidden={isNarrow && open ? true : undefined}
              aria-atomic="true"
            >
              {count}
            </span>
            {actions ? (
              <Stack direction="row" gap={1} align="center">
                {actions}
              </Stack>
            ) : null}
          </Stack>
        ) : null}
      </Stack>
    </div>
  );
}
