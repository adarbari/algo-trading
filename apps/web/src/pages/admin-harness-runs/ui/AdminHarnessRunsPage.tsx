/**
 * Admin > Harness runs: every edge evaluation run, newest first, with what it measured and left
 * out, beside the chosen run's stored rows (a sheet on a phone). The chosen run comes from the
 * route (shareable); the page only lays the widgets out.
 */
import { Heading, MasterDetail, Stack } from '@algotrade/ui';

import { HarnessRunDetail } from '@/widgets/harness-run-detail';
import { HarnessRunList } from '@/widgets/harness-run-list';

export interface AdminHarnessRunsPageProps {
  /** The chosen run (from the URL), if any. */
  selected?: string | null;
  onSelect: (id: string) => void;
  /** Narrow only: the detail sheet was dismissed; the route clears the choice. */
  onClear: () => void;
}

export function AdminHarnessRunsPage({
  selected = null,
  onSelect,
  onClear,
}: AdminHarnessRunsPageProps) {
  return (
    <Stack gap={4}>
      <Heading level={1}>Harness runs</Heading>
      <MasterDetail
        columns="main-aside"
        collapse="lg"
        master={<HarnessRunList selected={selected} onSelect={onSelect} />}
        detail={<HarnessRunDetail id={selected} />}
        detailKey={selected}
        detailTitle={selected ?? ''}
        onDetailClose={onClear}
      />
    </Stack>
  );
}
