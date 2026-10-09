/**
 * "Edge signals" at the top of Ideas: what the edges the user follows say to buy tonight, what to
 * sell next session and how each followed edge is doing (its live record). Each list is the
 * server's paper record for the session; a row opens its ticker in Explore (through the edge's
 * name) or its edge. With no followed edge it is one line pointing to Edges. This widget loads on
 * demand, so the Ideas page's first paint does not carry it.
 */
import { Button, DataTable, Heading, Panel, Stack } from '@algotrade/ui';

import { useEdgeDesk, type DeskTrade } from '@/entities/edge';
import { GuideHelp } from '@/features/guide-help';

import { buyColumns, followedColumns, sellColumns } from '../model/columns';

export interface EdgeSignalsProps {
  /** Open a ticker in Explore, with the edge (its id) that signalled it. */
  onOpen: (symbol: string, via: string) => void;
  /** Open an edge's page. */
  onOpenEdge: (edgeId: string) => void;
  /** Open the Edges list (where an edge is followed). */
  onOpenEdges: () => void;
}

const tradeId = (t: DeskTrade) => `${t.edgeId}:${t.instrumentId}`;

export function EdgeSignals({ onOpen, onOpenEdge, onOpenEdges }: EdgeSignalsProps) {
  const desk = useEdgeDesk();
  if (desk.isPending) {
    return <Panel title="Edge signals" state="loading" loadingLabel="Loading edge signals…" />;
  }
  if (desk.isError && !desk.data) {
    return (
      <Panel
        title="Edge signals"
        state="error"
        errorMessage="The edge signals failed to load."
        onRetry={() => void desk.refetch()}
      />
    );
  }
  const data = desk.data;
  if (!data || data.followed.length === 0) {
    return (
      <Stack direction="row">
        <Button size="sm" variant="ghost" onClick={onOpenEdges}>
          Follow an edge to see what it says to buy and sell
        </Button>
      </Stack>
    );
  }
  const open = (t: DeskTrade) => {
    onOpen(t.instrument?.symbol ?? t.instrumentId, t.edgeId);
  };
  return (
    <Panel
      title="Edge signals"
      actions={<GuideHelp entry={{ kind: 'term', id: 'paper_trading' }} />}
    >
      <Stack gap={3}>
        <Stack gap={1}>
          <Heading level={3}>Buy tonight</Heading>
          <DataTable<DeskTrade>
            label="Buy tonight"
            columns={buyColumns}
            rows={data.buys}
            getRowId={tradeId}
            onRowActivate={open}
            emptyMessage="Nothing to buy tonight"
            visibleRows={6}
          />
        </Stack>
        <Stack gap={1}>
          <Heading level={3}>Sell next session</Heading>
          <DataTable<DeskTrade>
            label="Sell next session"
            columns={sellColumns}
            rows={data.sells}
            getRowId={tradeId}
            onRowActivate={open}
            emptyMessage="Nothing to sell next session"
            visibleRows={6}
          />
        </Stack>
        <Stack gap={1}>
          <Heading level={3}>Followed edges</Heading>
          <DataTable
            label="Followed edges"
            columns={followedColumns}
            rows={data.followed}
            getRowId={(f) => f.edgeId}
            onRowActivate={(f) => {
              onOpenEdge(f.edgeId);
            }}
            emptyMessage="No followed edges"
            visibleRows={6}
          />
        </Stack>
      </Stack>
    </Panel>
  );
}
