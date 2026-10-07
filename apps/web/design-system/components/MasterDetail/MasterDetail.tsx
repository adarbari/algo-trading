/**
 * MasterDetail: a list beside its detail (the ticker table and the focused ticker's tabs, a
 * screener's picks and the pick under review). Wide, the two sit side by side in a Grid; when
 * the component's own width is under the `collapse` breakpoint (a phone) the master takes the
 * width, an optional summary (a compare bar, a "Detail for" picker) sits above it, and the
 * detail opens in a side sheet (Drawer) each time `detailKey` names a new item. Dismissing the
 * sheet calls `onDetailClose`; the caller clears its key there, so choosing the same item again
 * reopens it.
 */
import { useState, type ReactNode } from 'react';

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
  const open = narrow && detailKey !== null && dismissed !== detailKey;
  return (
    <div ref={ref} className={styles.root} data-layout={narrow ? 'narrow' : 'wide'}>
      {narrow ? (
        <Stack gap={gap}>
          {summary}
          {master}
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
        </Stack>
      ) : (
        <Grid columns={columns} gap={gap} align="start">
          {master}
          {summary === undefined ? (
            detail
          ) : (
            <Stack gap={3}>
              {summary}
              {detail}
            </Stack>
          )}
        </Grid>
      )}
    </div>
  );
}
