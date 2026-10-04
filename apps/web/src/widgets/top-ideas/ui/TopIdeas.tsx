/**
 * "Top ideas": one row per ticker with every screener that picked it, ranked by the user's
 * screener priority then score. Filter by decision, hide near-term earnings, tick tickers to
 * compare them in Explore, or click one to open it there.
 */
import { Chip, DataTable, Panel, Stack } from '@algotrade/ui';
import { useMemo, useState } from 'react';

import { CompareIdeasButton, type IdeaCompareSearch } from '@/features/idea-compare';
import { decisionLabel, useIdeas, type Idea } from '@/entities/idea';

import { ideaColumns } from '../model/columns';
import {
  decisionsPresent,
  EARNINGS_SOON_DAYS,
  filterIdeas,
  NO_FILTERS,
  type IdeaFilters,
} from '../model/filters';

export interface TopIdeasProps {
  onCompare: (search: IdeaCompareSearch) => void;
  onOpen: (symbol: string) => void;
}

export function TopIdeas({ onCompare, onOpen }: TopIdeasProps) {
  const ideas = useIdeas();
  const [filters, setFilters] = useState<IdeaFilters>(NO_FILTERS);
  const [selected, setSelected] = useState<string[]>([]);
  const all = useMemo(() => ideas.data?.ideas ?? [], [ideas.data]);
  const rows = useMemo(() => filterIdeas(all, filters), [all, filters]);
  const symbols = selected.flatMap((id) => {
    const symbol = all.find((idea) => idea.instrumentId === id)?.symbol;
    return symbol ? [symbol] : [];
  });

  const toggleDecision = (decision: string, on: boolean) => {
    setFilters((f) => ({
      ...f,
      decisions: on ? [...f.decisions, decision] : f.decisions.filter((d) => d !== decision),
    }));
  };
  const state = ideas.isError && !ideas.data ? 'error' : ideas.isPending ? 'loading' : 'ready';

  return (
    <Panel
      title="Top ideas · across all your screeners"
      description={ideas.data ? `Session ${ideas.data.session}` : undefined}
      flush
      state={state}
      loadingLabel="Loading ideas…"
      errorMessage="The ideas failed to load."
      onRetry={() => void ideas.refetch()}
      actions={
        <Stack direction="row" gap={2} align="center" wrap>
          {decisionsPresent(all).map((decision) => (
            <Chip
              key={decision}
              label={decisionLabel(decision)}
              selected={filters.decisions.includes(decision)}
              onSelectedChange={(on) => {
                toggleDecision(decision, on);
              }}
            />
          ))}
          <Chip
            label={`Hide earnings < ${EARNINGS_SOON_DAYS}d`}
            selected={filters.hideEarningsSoon}
            onSelectedChange={(on) => {
              setFilters((f) => ({ ...f, hideEarningsSoon: on }));
            }}
          />
          <CompareIdeasButton symbols={symbols} onCompare={onCompare} />
        </Stack>
      }
    >
      <DataTable<Idea>
        label="Top ideas"
        columns={ideaColumns}
        rows={rows}
        getRowId={(idea) => idea.instrumentId}
        getRowLabel={(idea) => idea.symbol ?? idea.instrumentId}
        defaultSort={{ columnId: 'rank', direction: 'asc' }}
        selectable
        selectedIds={selected}
        onSelectionChange={setSelected}
        onRowActivate={(idea) => {
          if (idea.symbol) onOpen(idea.symbol);
        }}
        emptyMessage={
          all.length === 0
            ? 'No screener picked anything in this session.'
            : 'No idea matches these filters.'
        }
        visibleRows={14}
      />
    </Panel>
  );
}
