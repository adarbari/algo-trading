/**
 * Trader > Edges, the Edges Lab (read-only): the edges grouped by verdict, and the chosen edge's
 * page in place of the list (a back button returns). The chosen edge comes from the route
 * (shareable).
 */
import { Button, Heading, Stack, Text } from '@algotrade/ui';

import type { EdgeView } from '@/entities/edge';

import { EdgeDetail } from '@/widgets/edge-detail';
import { EdgeList } from '@/widgets/edge-list';

export interface EdgesPageProps {
  /** The chosen edge (from the URL), or null for the list. */
  selected?: string | null;
  onSelect: (id: string) => void;
  /** Open the builder on one of the user's edges (null: a new edge). */
  onBuild: (id: string | null) => void;
  /** Back to the list: the route clears the choice. */
  onClear: () => void;
  /** The list's view (from the URL) and its change. */
  view?: EdgeView;
  onViewChange?: (view: EdgeView) => void;
}

export function EdgesPage({
  selected = null,
  onSelect,
  onBuild,
  onClear,
  view,
  onViewChange,
}: EdgesPageProps) {
  if (selected !== null) return <EdgeDetail id={selected} onBack={onClear} onEdit={onBuild} />;
  return (
    <Stack gap={3}>
      <Stack direction="row" gap={3} align="center" justify="between" wrap>
        <Stack gap={1}>
          <Heading level={1}>Edges</Heading>
          <Text size="sm" tone="secondary">
            Strategy ideas, each backtested for an edge
          </Text>
        </Stack>
        <Button
          variant="primary"
          onClick={() => {
            onBuild(null);
          }}
        >
          New edge
        </Button>
      </Stack>
      <EdgeList
        onSelect={onSelect}
        {...(view ? { view } : {})}
        {...(onViewChange ? { onViewChange } : {})}
      />
    </Stack>
  );
}
