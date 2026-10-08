/**
 * "Top ideas": one row per ticker with every screener that picked it, ranked by the user's
 * screener priority then score (on the server). Filter by decision, hide earnings within 14
 * sessions, tick tickers to compare them in Explore, or click one to open it there.
 */
import { Button, Chip, DataTable, Panel, Stack, Text } from '@algotrade/ui';
import { useMemo, useState } from 'react';

import { helped } from '@/features/guide-help';
import { CompareIdeasButton, type IdeaCompareSearch } from '@/features/idea-compare';
import { useIdeas, type Idea } from '@/entities/idea';
import { decisionLabel } from '@/entities/screen';

import { ideaColumns } from '../model/columns';
import {
  decisionsPresent,
  EARNINGS_SOON_LABEL,
  filterIdeas,
  NO_FILTERS,
  type IdeaFilters,
} from '../model/filters';

export interface TopIdeasProps {
  onCompare: (search: IdeaCompareSearch) => void;
  onOpen: (symbol: string) => void;
  /** Open a screener's results (a screener chip in a row). */
  onOpenScreener: (screenerId: string) => void;
  /** Open the Screeners list (where a screener is run). */
  onScreeners: () => void;
}

export function TopIdeas({ onCompare, onOpen, onOpenScreener, onScreeners }: TopIdeasProps) {
  const ideas = useIdeas();
  const [filters, setFilters] = useState<IdeaFilters>(NO_FILTERS);
  const [selected, setSelected] = useState<string[]>([]);
  const all = useMemo(() => ideas.data?.ideas ?? [], [ideas.data]);
  const columns = useMemo(() => ideaColumns(all, onOpenScreener), [all, onOpenScreener]);
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
  // Nothing stored yet (`ideas: null`), or no screener ran for the session (each NOT_RUN):
  // not an error, an empty panel that says so.
  const ran = ideas.data?.screeners.some((s) => s.notRun === null) ?? false;
  const state =
    ideas.isError && !ideas.data
      ? 'error'
      : ideas.isPending
        ? 'loading'
        : ideas.data.session === null || !ran
          ? 'empty'
          : 'ready';

  return (
    <Panel
      title="Top ideas · across all your screeners"
      description={ideas.data?.session ? `Session ${ideas.data.session}` : undefined}
      flush
      state={state}
      loadingLabel="Loading ideas…"
      emptyMessage={
        <Stack gap={2} align="start">
          <Text tone="muted">
            {ideas.data?.session
              ? 'No screener has run for this session, so there are no ideas.'
              : 'No screener has run yet, so there are no ideas.'}
          </Text>
          <Button variant="primary" onClick={onScreeners}>
            Go to Screeners
          </Button>
        </Stack>
      }
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
            label={EARNINGS_SOON_LABEL}
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
        columns={columns.map(helped)}
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
        canActivate={(idea) => Boolean(idea.symbol)}
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
