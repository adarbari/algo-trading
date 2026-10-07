/**
 * See it on a ticker: the field's stored values for one symbol over the last year as a line, with
 * the zone the chosen criterion passes shaded, and a link that opens Explore on that symbol with
 * the field. The window ends at the session the universe read is for, never the browser's today.
 */
import { Chart, EmptyState, Field, Input, Panel, Stack, Text, TextLink } from '@algotrade/ui';
import { useState } from 'react';

import {
  featureFormat,
  isNumericFeature,
  bandOf,
  useFeatureDistribution,
  type CatalogueFeature,
  type GuideUse,
} from '@/entities/feature';
import { exploreFieldPath } from '@/entities/guide';
import { pointsOf, useFeatureHistory } from '@/entities/instrument';
import { addDays } from '@/shared/lib';

const WINDOW_DAYS = 365;

export interface SeriesPanelProps {
  feature: CatalogueFeature;
  /** The symbol shown (null: none chosen yet). */
  symbol: string | null;
  onSymbolChange: (symbol: string) => void;
  /** The criterion whose passing zone is shaded (none: nothing shaded). */
  use: GuideUse | undefined;
}

/** The symbol box: edits stay in the box until Enter or leaving it, so each letter is not a request. */
function SymbolField({ symbol, onCommit }: { symbol: string; onCommit: (symbol: string) => void }) {
  const [draft, setDraft] = useState(symbol);
  const commit = () => {
    const next = draft.trim().toUpperCase();
    if (next && next !== symbol) onCommit(next);
  };
  return (
    <Field label="Symbol" layout="inline">
      <Input
        mono
        size="sm"
        width="auto"
        value={draft}
        onValueChange={setDraft}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === 'Enter') commit();
        }}
        spellCheck={false}
        autoComplete="off"
      />
    </Field>
  );
}

function History({
  feature,
  symbol,
  use,
}: {
  feature: CatalogueFeature;
  symbol: string;
  use: GuideUse | undefined;
}) {
  const session = useFeatureDistribution(feature.name).data?.session ?? null;
  const start = session ? addDays(session, -WINDOW_DAYS) : null;
  const history = useFeatureHistory(symbol, [feature.name], start, session);
  const band = use ? bandOf(use) : null;
  return (
    <Stack gap={2}>
      <Chart
        label={`${symbol} ${feature.name}`}
        series={[{ id: feature.name, label: symbol, points: pointsOf(history, feature.name) }]}
        range="All"
        format={featureFormat(feature)}
        height="md"
        {...(use && band
          ? { valueBands: [{ ...band, tone: 'accent' as const, label: use.intent }] }
          : {})}
        status={session === null || history.isPending ? 'loading' : 'ready'}
        emptyMessage={`No ${feature.name} stored for ${symbol} in the last year.`}
      />
      <Text size="sm" tone="muted">
        {use && band
          ? `Shaded: where “${use.intent}” passes.`
          : 'Gaps are sessions with no stored value.'}
      </Text>
    </Stack>
  );
}

export function SeriesPanel({ feature, symbol, onSymbolChange, use }: SeriesPanelProps) {
  const stored = isNumericFeature(feature) && !feature.name.startsWith('instrument.');
  return (
    <Panel
      title="See it on a ticker"
      footer={
        symbol === null ? undefined : (
          <TextLink href={exploreFieldPath(feature.name, symbol)} size="sm">
            Open in Explore with its history
          </TextLink>
        )
      }
      actions={<SymbolField key={symbol ?? ''} symbol={symbol ?? ''} onCommit={onSymbolChange} />}
    >
      {!stored ? (
        <EmptyState
          compact
          title="No history for this field"
          description="Only numeric catalogue fields with a stored history are drawn over time."
        />
      ) : symbol === null ? (
        <EmptyState
          compact
          title="Enter a symbol"
          description="Type a ticker above to see this field over the last year."
        />
      ) : (
        <History feature={feature} symbol={symbol} use={use} />
      )}
    </Panel>
  );
}
