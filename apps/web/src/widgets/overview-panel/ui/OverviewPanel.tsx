/**
 * Overview: what the focused ticker is, for the latest session. Name, kind and sector, the
 * stored description, the headline numbers (price, market cap, P/E, revenue, next earnings)
 * and grouped key facts (size, price range, dividends, options, earnings dates), all from one
 * GraphQL read (`useInstrumentFacts`), then "In rough markets": beta to SPY and the drawdown
 * in each reference episode (`model/rough-markets.ts`). A value the session does not have says
 * why (UNKNOWN and its reason); what the nightly tables missing for the session leave out is told by kind in a
 * banner. An ETF also shows the `fund` section the page passes in (its holdings).
 */
import {
  Chip,
  formatValue,
  Grid,
  Heading,
  KeyValue,
  Panel,
  StatStrip,
  Stack,
  Text,
} from '@algotrade/ui';
import type { ReactNode } from 'react';
import { useMemo } from 'react';

import { featureTitle } from '@/entities/feature';
import { UnavailableNote } from '@/entities/availability';
import { useInstrumentEvents, useInstrumentFacts } from '@/entities/instrument';
import { useRegimeEpisodes } from '@/entities/regime';

import {
  earningsGroup,
  factGroups,
  headlineStats,
  OVERVIEW_FEATURES,
  profileOf,
  valuesOf,
} from '../model/overview';
import { ROUGH_MARKET_FEATURES, roughMarketsGroup } from '../model/rough-markets';

const FEATURES = [...OVERVIEW_FEATURES, ...ROUGH_MARKET_FEATURES];

export interface OverviewPanelProps {
  symbol: string;
  /** Shown under the facts for an ETF (its holdings). */
  fund?: ReactNode;
}

export function OverviewPanel({ symbol, fund }: OverviewPanelProps) {
  const facts = useInstrumentFacts(symbol, FEATURES);
  const events = useInstrumentEvents(symbol);
  const episodes = useRegimeEpisodes();
  const view = useMemo(() => {
    const instrument = facts.data?.instrument;
    if (!instrument) return null;
    const values = valuesOf(instrument);
    const groups = factGroups(values);
    const earnings = earningsGroup(values, events.data ?? []);
    // The plain names come from the API: the group waits for them rather than flash keys
    const rough = roughMarketsGroup(values, episodes.data?.episodes ?? []);
    return {
      profile: profileOf(instrument, values),
      stats: headlineStats(values),
      groups: [
        ...groups.slice(0, 2),
        earnings,
        ...groups.slice(2),
        ...(rough.items.length > 0 && !episodes.isPending ? [rough] : []),
      ],
    };
  }, [facts.data, events.data, episodes.data, episodes.isPending]);
  const session = facts.data?.session;
  const profile = view?.profile;
  const day = session ? formatValue(session.date, { kind: 'date' }).text : '';
  const state = facts.isError
    ? 'error'
    : facts.isPending
      ? 'loading'
      : view === null
        ? 'empty'
        : 'ready';
  return (
    <Stack gap={4}>
      <Panel
        title={`${symbol} · overview`}
        description={profile?.name || undefined}
        state={state}
        loadingLabel={`Loading ${symbol}…`}
        errorMessage={`${symbol} failed to load.`}
        emptyMessage={`${symbol} is not in the reference snapshot for ${day || 'the session'}.`}
        onRetry={() => void facts.refetch()}
        footer={session ? `Values for the session of ${day}.` : undefined}
      >
        {view && profile && (
          <Stack gap={4}>
            <UnavailableNote gaps={session?.unavailable ?? []} titleOf={featureTitle} />
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
