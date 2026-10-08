/**
 * The user's screeners as a sortable list: drag (or Space and arrows) to reorder; each move is
 * saved at once and the Ideas ranking follows the new priority. A click on a screener's row
 * opens its results (its name is the keyboard's button).
 */
import { SortableList } from '@algotrade/ui';

import { ScreenerRow, type ScreenerSummary } from '@/entities/idea';

import { useSavePriority } from '../api/hooks';

export interface ScreenerPriorityListProps {
  screeners: readonly ScreenerSummary[];
  /** Open a screener's results (a click on its row, or its name's button). */
  onOpenScreener?: (screenerId: string) => void;
}

export function ScreenerPriorityList({ screeners, onOpenScreener }: ScreenerPriorityListProps) {
  const save = useSavePriority();
  return (
    <SortableList<ScreenerSummary>
      label="Screener priority"
      items={screeners}
      getKey={(s) => s.id}
      getLabel={(s) => s.name}
      renderItem={(screener, { index }) => (
        <ScreenerRow
          screener={screener}
          rank={index + 1}
          {...(onOpenScreener ? { onOpen: onOpenScreener } : {})}
        />
      )}
      {...(onOpenScreener
        ? {
            onActivate: (s: ScreenerSummary) => {
              onOpenScreener(s.id);
            },
          }
        : {})}
      onReorder={(next) => {
        save.mutate(next.map((s) => s.id));
      }}
    />
  );
}
