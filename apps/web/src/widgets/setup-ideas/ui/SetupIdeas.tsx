/**
 * One Ideas tab from the picks of setups with a good stored verdict (ADR 0083 decision 2): the
 * setups grouped strongest first, each with its verdict, the backtested (hypothetical) figures
 * the verdict rests on and the names it picked tonight; a row beside its detail (`MasterDetail`,
 * a sheet on a phone). When no setup of the tab qualifies the server says `unproven` and the
 * `unproven` content (the tab's pool of screeners) is shown instead, labelled Unproven, with the
 * counts of what was left out. Everything shown is the server's: this widget lays it out.
 */
import {
  Button,
  DataTable,
  Heading,
  KeyValue,
  MasterDetail,
  Panel,
  Stack,
  StatusBadge,
  Text,
} from '@algotrade/ui';
import { useState, type ReactNode } from 'react';

import { verdictLabel, verdictTone } from '@/entities/edge';
import { useSetupIdeas, type IdeaTab, type SetupGroup, type SetupIdea } from '@/entities/idea';
import { termHelp } from '@/features/guide-help';

import { pickColumns } from '../model/columns';
import { LEFT_OUT_TERMS, STATE_TERMS } from '../model/terms';

export interface SetupIdeasProps {
  tab: IdeaTab;
  /** The tab's Unproven section: shown when no setup of the tab qualifies. */
  unproven: ReactNode;
  /** Open a ticker in Explore, with the screener (config id) its setup rests on. */
  onOpen: (symbol: string, via: string) => void;
  /** Open a setup's page. */
  onOpenEdge: (edgeId: string) => void;
  /** Open a name's idea page under the setup that ranks it. */
  onOpenIdea: (symbol: string, setupId: string) => void;
}

function GroupHeader({
  group,
  onOpenEdge,
}: {
  group: SetupGroup;
  onOpenEdge: (id: string) => void;
}) {
  const night = STATE_TERMS[group.state];
  return (
    <Stack gap={1}>
      <Stack direction="row" gap={2} align="center" wrap>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            onOpenEdge(group.edgeId);
          }}
        >
          {group.name}
        </Button>
        <StatusBadge tone={verdictTone(group.level)}>{verdictLabel(group.level)}</StatusBadge>
        {night && group.state !== 'picked' && (
          <Stack direction="row" gap={1} align="center">
            <Text size="sm" tone="muted">
              {night.label}
            </Text>
            {termHelp(night.term)}
          </Stack>
        )}
      </Stack>
      <Text size="sm" tone="muted">
        {[
          'Backtested (hypothetical)',
          group.liftPts === null ? null : `lift ${group.liftPts.toFixed(1)} pts`,
          group.oosTrades === null ? null : `${group.oosTrades} out-of-sample trades`,
          group.basisHorizon === null ? null : `${group.basisHorizon}-day hold`,
        ]
          .filter((part) => part !== null)
          .join(' · ')}
      </Text>
    </Stack>
  );
}

function Detail({
  idea,
  group,
  onOpen,
  onOpenEdge,
  onOpenIdea,
}: {
  idea: SetupIdea;
  group: SetupGroup | undefined;
  onOpen: SetupIdeasProps['onOpen'];
  onOpenEdge: SetupIdeasProps['onOpenEdge'];
  onOpenIdea: SetupIdeasProps['onOpenIdea'];
}) {
  const symbol = idea.symbol;
  return (
    <Stack gap={3}>
      <Heading level={3}>{symbol ?? idea.instrumentId}</Heading>
      <KeyValue
        label="Idea"
        items={[
          { label: 'Setup', value: group?.name ?? idea.setupId },
          { label: 'Place in the setup', value: idea.place },
          ...(idea.regime ? [{ label: 'Regime', value: idea.regime }] : []),
          ...idea.metrics.map((m) => ({ label: m.name, value: m.value })),
        ]}
      />
      {idea.watchOut.length > 0 && (
        <Stack direction="row" gap={2} align="center" wrap>
          {idea.watchOut.map((w) => (
            <StatusBadge key={w} tone="warning">
              {w.replaceAll('_', ' ')}
            </StatusBadge>
          ))}
        </Stack>
      )}
      <Stack direction="row" gap={2} wrap>
        {symbol && (
          <Button
            variant="primary"
            onClick={() => {
              onOpenIdea(symbol, idea.setupId);
            }}
          >
            Open the idea
          </Button>
        )}
        {symbol && group && (
          <Button
            variant="secondary"
            onClick={() => {
              onOpen(symbol, group.basisScreener);
            }}
          >
            {`Open ${symbol} in Explore`}
          </Button>
        )}
        <Button
          variant="secondary"
          onClick={() => {
            onOpenEdge(idea.setupId);
          }}
        >
          Open the setup
        </Button>
      </Stack>
    </Stack>
  );
}

export function SetupIdeas({ tab, unproven, onOpen, onOpenEdge, onOpenIdea }: SetupIdeasProps) {
  const found = useSetupIdeas(tab);
  const [chosen, setChosen] = useState<string | null>(null);
  const data = found.data;
  if (found.isPending || found.isError || !data) {
    return (
      <Panel
        title="Ideas from setups"
        actions={termHelp('ideas_listed')}
        state={found.isPending ? 'loading' : found.isError ? 'error' : 'empty'}
        loadingLabel="Loading ideas…"
        errorMessage="The ideas failed to load."
        emptyMessage="Nothing is stored for this session yet."
        onRetry={() => void found.refetch()}
      />
    );
  }
  const left = data.leftOut.flatMap((c) => {
    const known = LEFT_OUT_TERMS[c.kind];
    return known ? [{ ...known, count: c.count, kind: c.kind }] : [];
  });
  const counts = left.length > 0 && (
    <Stack direction="row" gap={3} align="center" wrap>
      {left.map((c) => (
        <Stack key={c.kind} direction="row" gap={1} align="center">
          <Text size="sm" tone="muted">{`${c.count} ${c.label}`}</Text>
          {termHelp(c.term)}
        </Stack>
      ))}
    </Stack>
  );
  if (data.state === 'unproven') {
    return (
      <Stack gap={3}>
        <Stack direction="row" gap={2} align="center" wrap>
          <StatusBadge tone="warning">Unproven</StatusBadge>
          {termHelp('ideas_unproven')}
          {counts}
        </Stack>
        {unproven}
      </Stack>
    );
  }
  const names = new Map(data.groups.map((g) => [g.edgeId, g.name]));
  const idea = data.ideas.find((i) => i.instrumentId === chosen) ?? null;
  return (
    <Stack gap={3}>
      {counts}
      <MasterDetail
        master={
          <Stack gap={4}>
            {data.groups.map((g) => (
              <Stack key={g.edgeId} gap={2}>
                <GroupHeader group={g} onOpenEdge={onOpenEdge} />
                {g.ideas.length > 0 && (
                  <DataTable<SetupIdea>
                    label={`${g.name} picks`}
                    columns={pickColumns(names)}
                    rows={g.ideas}
                    getRowId={(i) => i.instrumentId}
                    getRowLabel={(i) => i.symbol ?? i.instrumentId}
                    selectable={false}
                    onRowActivate={(i) => {
                      setChosen(i.instrumentId);
                    }}
                    defaultSort={{ columnId: 'rank', direction: 'asc' }}
                  />
                )}
              </Stack>
            ))}
          </Stack>
        }
        detailKey={idea?.instrumentId ?? null}
        detailTitle={idea?.symbol ?? idea?.instrumentId ?? ''}
        onDetailClose={() => {
          setChosen(null);
        }}
        detail={
          idea ? (
            <Detail
              idea={idea}
              group={data.groups.find((g) => g.edgeId === idea.setupId)}
              onOpen={onOpen}
              onOpenEdge={onOpenEdge}
              onOpenIdea={onOpenIdea}
            />
          ) : (
            <Text tone="muted">Choose a name to see its setup.</Text>
          )
        }
      />
    </Stack>
  );
}
