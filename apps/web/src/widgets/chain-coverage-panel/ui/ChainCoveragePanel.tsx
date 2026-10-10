/**
 * Option-chain coverage of the served session: the share of the optionable names whose chain
 * was fetched OK, the status counts and tiers, and the names the feed keeps serving stale. A
 * coverage that fell or a chronic count that rose is the server's drift warning, shown in text.
 */
import {
  EmptyState,
  ErrorState,
  formatValue,
  Mono,
  Panel,
  Skeleton,
  Stack,
  StatStrip,
  Text,
  type StatItem,
} from '@algotrade/ui';

import { useChainCoverage, type ChainCoverage } from '@/entities/ingestion';
import { termHelp } from '@/features/guide-help';

const count = (n: number) => formatValue(n, { kind: 'number' }).text;

function stats(c: ChainCoverage): StatItem[] {
  const drifted = c.drift.length > 0;
  return [
    {
      id: 'coverage',
      label: 'Chain coverage',
      value: c.share,
      format: { kind: 'percent', digits: 1 },
      tone: drifted ? 'warning' : 'default',
      sub: `${count(c.ok)} of ${count(c.total)} optionable`,
    },
    {
      id: 'chronic',
      label: 'Chronic stale names',
      value: count(c.chronic),
      tone: c.chronic > 0 ? 'warning' : 'default',
      sub:
        c.previousChronic === null ? undefined : `${count(c.previousChronic)} the session before`,
    },
    ...c.tiers.map((t) => ({
      id: `tier-${t.tier}`,
      label: `${t.tier} tier`,
      value: `${count(t.ok)} of ${count(t.total)} OK`,
      sub: `${count(t.stale)} stale`,
    })),
    {
      id: 'statuses',
      label: 'By status',
      value: c.statuses.map((s) => `${s.code} ${count(s.count)}`).join(' · '),
    },
  ];
}

export function ChainCoveragePanel() {
  const coverage = useChainCoverage();
  const data = coverage.data;
  return (
    <Panel
      title="Option chain coverage"
      description={data ? formatValue(data.session, { kind: 'date', style: 'weekday' }).text : ''}
      actions={termHelp('chain_coverage')}
    >
      {coverage.isPending ? (
        <Skeleton variant="rect" height="md" label="Loading chain coverage…" />
      ) : coverage.isError ? (
        <ErrorState
          compact
          title="Chain coverage could not load."
          detail={coverage.error.message}
          onRetry={() => void coverage.refetch()}
          retrying={coverage.isFetching}
        />
      ) : !data ? (
        <EmptyState compact title="No chains run for this session" />
      ) : (
        <Stack gap={3}>
          <StatStrip label="Chain coverage" items={stats(data)} />
          {data.drift.map((d) => (
            <Text key={d} tone="warning">
              {d}
            </Text>
          ))}
          {data.chronicNames.length > 0 && <Mono>{data.chronicNames.join(', ')}</Mono>}
        </Stack>
      )}
    </Panel>
  );
}
