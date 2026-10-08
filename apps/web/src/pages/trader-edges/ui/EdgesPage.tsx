/**
 * Trader > Edges: the edges and what their frozen periods say, the list beside the chosen
 * edge's detail (a sheet on a phone). The chosen edge comes from the route (shareable).
 */
import { Heading, MasterDetail, Stack, Text } from '@algotrade/ui';

import { EdgeDetail } from '@/widgets/edge-detail';
import { EdgeList } from '@/widgets/edge-list';

export interface EdgesPageProps {
  /** The chosen edge (from the URL), or null. */
  selected?: string | null;
  onSelect: (id: string) => void;
  /** Narrow only: the detail sheet was dismissed; the route clears the choice. */
  onClear: () => void;
}

export function EdgesPage({ selected = null, onSelect, onClear }: EdgesPageProps) {
  return (
    <Stack gap={3}>
      <Stack gap={1}>
        <Heading level={1}>Edges</Heading>
        <Text size="sm" tone="secondary">
          Each edge, tested on the stored history, and what its frozen period shows.
        </Text>
      </Stack>
      <MasterDetail
        columns="main-aside"
        collapse="lg"
        master={<EdgeList selected={selected} onSelect={onSelect} />}
        detail={<EdgeDetail id={selected} />}
        detailKey={selected}
        detailTitle={selected ?? ''}
        onDetailClose={onClear}
      />
    </Stack>
  );
}
