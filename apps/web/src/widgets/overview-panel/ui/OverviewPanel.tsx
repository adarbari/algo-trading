/**
 * Overview: what the focused ticker is. Name, kind and sector, the stored description, the
 * headline numbers (price, market cap, P/E, revenue, next earnings) and grouped key facts
 * (size, price range, dividends, options, earnings dates). Facts the store lacks are left out;
 * an ETF also shows the `fund` section the page passes in (its holdings).
 */
import { Chip, Grid, Heading, KeyValue, Panel, StatStrip, Stack, Text } from '@algotrade/ui';
import type { ReactNode } from 'react';
import { useMemo } from 'react';

import { useInstrument, useInstrumentEvents } from '@/entities/instrument';
import { todayIso } from '@/shared/lib';

import {
  earningsGroup,
  factGroups,
  headlineStats,
  nextEarningsDate,
  profileOf,
} from '../model/overview';

export interface OverviewPanelProps {
  symbol: string;
  /** Shown under the facts for an ETF (its holdings). */
  fund?: ReactNode;
}

export function OverviewPanel({ symbol, fund }: OverviewPanelProps) {
  const detail = useInstrument(symbol);
  const events = useInstrumentEvents(symbol);
  const view = useMemo(() => {
    if (!detail.data) return null;
    const today = todayIso();
    const found = events.data ?? [];
    const earnings = earningsGroup(detail.data, found, today);
    const groups = factGroups(detail.data);
    return {
      profile: profileOf(detail.data),
      stats: headlineStats(detail.data, nextEarningsDate(detail.data, found, today)),
      groups: earnings ? [...groups.slice(0, 2), earnings, ...groups.slice(2)] : groups,
    };
  }, [detail.data, events.data]);
  const profile = view?.profile;
  return (
    <Stack gap={4}>
      <Panel
        title={`${symbol} · overview`}
        description={profile?.name || undefined}
        state={detail.isError ? 'error' : detail.isPending ? 'loading' : 'ready'}
        loadingLabel={`Loading ${symbol}…`}
        errorMessage={`${symbol} failed to load.`}
        onRetry={() => void detail.refetch()}
      >
        {view && profile && (
          <Stack gap={4}>
            <Stack gap={2}>
              <Stack direction="row" gap={2} wrap>
                <Chip label={profile.kind} />
                {profile.sector && <Chip label={profile.sector} />}
                {profile.industry && profile.industry !== profile.sector && (
                  <Chip label={profile.industry} />
                )}
                {profile.exchange && <Chip label={profile.exchange} />}
                {profile.tags.map((tag) => (
                  <Chip key={tag} label={tag} />
                ))}
              </Stack>
              {profile.description ? (
                <Text as="p" tone="secondary">
                  {profile.description}
                </Text>
              ) : (
                <Text as="p" tone="muted">
                  No description stored for {symbol} yet.
                </Text>
              )}
              {profile.website && (
                <Text size="sm" tone="muted">
                  {profile.website}
                </Text>
              )}
            </Stack>
            <StatStrip
              label={`${symbol} headline numbers`}
              items={view.stats}
              emptyMessage="No price or fundamentals stored yet."
            />
            <Grid columns={2} gap={4} collapse="md">
              {view.groups.map((group) => (
                <Stack key={group.id} gap={2}>
                  <Heading level={3}>{group.title}</Heading>
                  <KeyValue label={group.title} items={group.items} alignValues="end" />
                </Stack>
              ))}
            </Grid>
          </Stack>
        )}
      </Panel>
      {profile?.isEtf && fund}
    </Stack>
  );
}
