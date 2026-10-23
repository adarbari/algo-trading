/**
 * Admin > Screener runs: every screener run, newest first, of any status, beside the chosen
 * run's record (a sheet on a phone). The chosen run and the filters come from the route
 * (shareable); the page only lays the widgets out.
 */
import { Heading, MasterDetail, Stack } from '@algotrade/ui';

import type { ScreenerRunFilters } from '@/entities/screener-run';
import { ScreenerRunDetail } from '@/widgets/screener-run-detail';
import { ScreenerRunList } from '@/widgets/screener-run-list';

export interface AdminScreenerRunsPageProps {
  /** The chosen run (from the URL), if any. */
  selected?: string | null;
  /** The list's filters (from the URL). */
  filters?: ScreenerRunFilters;
  onFiltersChange?: (filters: ScreenerRunFilters) => void;
  onSelect: (id: string) => void;
  /** Narrow only: the detail sheet was dismissed; the route clears the choice. */
  onClear: () => void;
}

export function AdminScreenerRunsPage({
  selected = null,
  filters,
  onFiltersChange,
  onSelect,
  onClear,
}: AdminScreenerRunsPageProps) {
  return (
    <Stack gap={4}>
      <Heading level={1}>Screener runs</Heading>
      <MasterDetail
        columns="main-aside"
        collapse="lg"
        master={
          <ScreenerRunList
            selected={selected}
            onSelect={onSelect}
            {...(filters ? { filters } : {})}
            {...(onFiltersChange ? { onFiltersChange } : {})}
          />
        }
        detail={<ScreenerRunDetail id={selected} />}
        detailKey={selected}
        detailTitle={selected ?? ''}
        onDetailClose={onClear}
      />
    </Stack>
  );
}
