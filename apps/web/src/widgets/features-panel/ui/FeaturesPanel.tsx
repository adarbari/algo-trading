/**
 * Features: every catalogue feature for the focused ticker (value, unit, kind, definition,
 * a sparkline of the last 90 days for numbers), searchable; choosing a row shows that
 * feature's distribution across the universe with the ticker marked.
 */
import { DataTable, EmptyState, Panel, SearchInput, Stack } from '@algotrade/ui';
import { useMemo, useState } from 'react';

import { useFeatureCatalogue } from '@/entities/feature';
import { useFeatureHistory, useInstrument } from '@/entities/instrument';
import { addDays, todayIso } from '@/shared/lib';

import { featureColumns, featureRows, filterRows, type FeatureRow } from '../model/rows';

import { FeatureDistribution } from './FeatureDistribution';

const HISTORY_DAYS = 90;

export interface FeaturesPanelProps {
  symbol: string;
  /** The feature whose distribution is shown (null: none yet). */
  feature: string | null;
  onFeatureChange: (name: string) => void;
}

export function FeaturesPanel({ symbol, feature, onFeatureChange }: FeaturesPanelProps) {
  const [query, setQuery] = useState('');
  const catalogue = useFeatureCatalogue();
  const detail = useInstrument(symbol);
  const history = useFeatureHistory(symbol, addDays(todayIso(), -HISTORY_DAYS));
  const rows = useMemo(
    () => featureRows(catalogue.data ?? [], detail.data, history.data),
    [catalogue.data, detail.data, history.data],
  );
  const shown = useMemo(() => filterRows(rows, query), [rows, query]);
  const columns = useMemo(() => featureColumns(symbol), [symbol]);
  const chosen = rows.find((r) => r.feature.name === feature);
  const failed = catalogue.isError || detail.isError;
  return (
    <Stack gap={4}>
      <Panel
        title={`${symbol} · features`}
        description={history.isPending ? 'Loading history…' : `${rows.length} catalogue features`}
        flush
        state={failed ? 'error' : 'ready'}
        errorMessage={`${symbol} features failed to load.`}
        onRetry={() => {
          void catalogue.refetch();
          void detail.refetch();
        }}
      >
        <DataTable<FeatureRow>
          label={`${symbol} features`}
          columns={columns}
          rows={shown}
          getRowId={(r) => r.feature.name}
          rowLines={2}
          visibleRows={12}
          onRowActivate={(r) => {
            onFeatureChange(r.feature.name);
          }}
          status={catalogue.isPending || detail.isPending ? 'loading' : 'ready'}
          emptyMessage={`No feature matches “${query}”`}
          toolbar={
            <SearchInput
              aria-label="Filter features"
              placeholder="Feature name or definition…"
              size="sm"
              value={query}
              onValueChange={setQuery}
            />
          }
        />
      </Panel>
      {chosen ? (
        <FeatureDistribution feature={chosen.feature} symbol={symbol} value={chosen.value} />
      ) : (
        <EmptyState
          compact
          title="Choose a feature"
          description={`Click a row to see how that feature is spread across the universe, with ${symbol} marked.`}
        />
      )}
    </Stack>
  );
}
