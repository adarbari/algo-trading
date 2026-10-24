/**
 * Admin > Screener runs: every screener run, newest first, of any status, beside the chosen
 * run's record (a sheet on a phone). The chosen run and the filters come from the route
 * (shareable); the page only lays the widgets out.
 */
import { Heading, MasterDetail, Stack } from '@algotrade/ui';

import { parseFilters } from '@/entities/screener-run';
import { ScreenerRunDetail } from '@/widgets/screener-run-detail';
import { ScreenerRunList } from '@/widgets/screener-run-list';

export interface AdminScreenerRunsPageProps {
  /** The URL's search object (`run` and the filters); anything else in it is dropped here. */
  search?: Record<string, unknown>;
  /** The URL's next search (the chosen run plus the filters); the route navigates to it. */
  onChange: (search: Record<string, unknown>) => void;
}

/** The chosen run and the filters in a URL's search object. */
export function readSearch(search: Record<string, unknown>) {
  const run = typeof search.run === 'string' && search.run ? search.run : null;
  return { selected: run, filters: parseFilters(search) };
}

export function AdminScreenerRunsPage({ search = {}, onChange }: AdminScreenerRunsPageProps) {
  const { selected, filters } = readSearch(search);
  return (
    <Stack gap={4}>
      <Heading level={1}>Screener runs</Heading>
      <MasterDetail
        columns="main-aside"
        collapse="lg"
        master={
          <ScreenerRunList
            selected={selected}
            onSelect={(run) => {
              onChange({ ...filters, run });
            }}
            filters={filters}
            onFiltersChange={(next) => {
              onChange({ ...(selected ? { run: selected } : {}), ...next });
            }}
          />
        }
        detail={<ScreenerRunDetail id={selected} />}
        detailKey={selected}
        detailTitle={selected ?? ''}
        onDetailClose={() => {
          onChange({ ...filters });
        }}
      />
    </Stack>
  );
}
