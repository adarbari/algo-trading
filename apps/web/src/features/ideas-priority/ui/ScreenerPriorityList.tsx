/**
 * The user's screeners as a sortable list: drag (or Space and arrows) to reorder; each move is
 * saved at once and the Ideas ranking follows the new priority.
 */
import { SortableList } from '@algotrade/ui';

import { ScreenerRow, type ScreenerSummary } from '@/entities/idea';

import { useSavePriority } from '../api/hooks';

export function ScreenerPriorityList({ screeners }: { screeners: readonly ScreenerSummary[] }) {
  const save = useSavePriority();
  return (
    <SortableList<ScreenerSummary>
      label="Screener priority"
      items={screeners}
      getKey={(s) => s.id}
      getLabel={(s) => s.name}
      renderItem={(screener, { index }) => <ScreenerRow screener={screener} rank={index + 1} />}
      onReorder={(next) => {
        save.mutate(next.map((s) => s.id));
      }}
    />
  );
}
