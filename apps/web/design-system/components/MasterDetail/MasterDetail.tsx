/**
 * MasterDetail: a list beside its detail (the ticker table and the focused ticker's tabs, a
 * screener's picks and the pick under review). Wide, the two sit side by side in a Grid; when
 * the component's own width is under the `collapse` breakpoint (a phone) the master takes the
 * width, an optional summary (a compare bar, a "Detail for" picker) sits above it, and the
 * detail opens in a side sheet (Drawer) each time `detailKey` names a new item. Dismissing the
 * sheet calls `onDetailClose`; the caller clears its key there, so choosing the same item again
 * reopens it.
 */
import { Fragment, useState, type ReactNode } from 'react';

import { Grid } from '../../primitives/Grid';
import { Stack } from '../../primitives/Stack';
import { useNarrow } from '../../responsive';
import type { Space } from '../../tokens';
import { Drawer } from '../Drawer';
import styles from './MasterDetail.module.css';

export interface MasterDetailProps {
  /** The list (a table of rows to choose from). */
  master: ReactNode;
  /** The chosen item's detail. Wide: always beside the master; narrow: in the sheet. */
  detail: ReactNode;
  /** The item the detail shows (null: none chosen). Narrow: a new non-null key opens the sheet. */
  detailKey: string | null;
  /** The sheet's heading and accessible name on narrow (the item's name, "AAPL"). */
  detailTitle: ReactNode;
  /** One line under the sheet's heading on narrow. */
  detailDescription?: ReactNode;
  /** Narrow only: the sheet was dismissed (Escape, close button, backdrop). */
  onDetailClose: () => void;
  /** Above the master on narrow, at the top of the detail column on wide (a compare bar). */
  summary?: ReactNode;
  /** Wide layout: two equal columns (default) or `main-aside` (3 : 2). */
  columns?: 2 | 'main-aside';
  /** Space between the columns, and between the summary and its neighbour (default 4). */
  gap?: Space;
  /** The breakpoint under which the detail moves into a sheet: `md` (720) or `lg` (960, default). */
  collapse?: 'md' | 'lg';
}

export function MasterDetail({
  master,
  detail,
  detailKey,
  detailTitle,
  detailDescription,
  onDetailClose,
  summary,
  columns = 2,
  gap = 4,
  collapse = 'lg',
}: MasterDetailProps) {
  const [ref, narrow] = useNarrow(collapse);
  // The key whose sheet the user dismissed; a different key (or the key cleared) reopens.
  const [dismissed, setDismissed] = useState<string | null>(null);
  const [shownKey, setShownKey] = useState(detailKey);
  if (shownKey !== detailKey) {
    setShownKey(detailKey);
    setDismissed(null);
  }
  // Crossing from wide to narrow (a window resized, a phone measured after the viewport guess
  // was wrong) must not pop a modal over a detail the user was already reading: the current
  // key counts as dismissed; the next choice opens the sheet.
  const [wasNarrow, setWasNarrow] = useState(narrow);
  if (wasNarrow !== narrow) {
    setWasNarrow(narrow);
    if (narrow) setDismissed(detailKey);
  }
  const open = narrow && detailKey !== null && dismissed !== detailKey;
  // One Grid at both widths, its children keyed, so the master keeps its instance (scroll,
  // active row, open pickers) when the width crosses the breakpoint.
  const children = narrow
    ? [
        summary === undefined ? null : <Fragment key="summary">{summary}</Fragment>,
        <Fragment key="master">{master}</Fragment>,
      ]
    : [
        <Fragment key="master">{master}</Fragment>,
        summary === undefined ? (
          <Fragment key="detail">{detail}</Fragment>
        ) : (
          <Stack key="detail" gap={3}>
            {summary}
            {detail}
          </Stack>
        ),
      ];
  return (
    <div ref={ref} className={styles.root} data-layout={narrow ? 'narrow' : 'wide'}>
      <Grid columns={narrow ? 1 : columns} gap={gap} align="start">
        {children}
      </Grid>
      {narrow ? (
        <Drawer
          open={open}
          onOpenChange={(next) => {
            if (next) return;
            setDismissed(detailKey);
            onDetailClose();
          }}
          title={detailTitle}
          description={detailDescription}
          side="end"
          size="lg"
        >
          {detail}
        </Drawer>
      ) : null}
    </div>
  );
}
