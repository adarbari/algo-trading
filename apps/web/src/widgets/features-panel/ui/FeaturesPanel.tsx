/**
 * Features: every catalogue feature for the focused ticker (its value for the session, unit,
 * kind, definition, a sparkline of the 90 days up to the session for numbers), searchable;
 * choosing a row shows that feature's distribution across the universe with the ticker
 * marked. Values and history come over GraphQL (`useFeatureValues`, `useFeatureHistory`);
 * the history window ends at the session the values are for, never the browser's today.
 */
import { DataTable, EmptyState, Panel, SearchInput, Stack } from '@algotrade/ui';
import { useMemo, useState } from 'react';

import { useFeatureCatalogue } from '@/entities/feature';
import { useFeatureHistory, useFeatureValues } from '@/entities/instrument';
import { addDays } from '@/shared/lib';

import {
  featureColumns,
  featureRows,
  filterRows,
  historyNames,
  type FeatureRow,
} from '../model/rows';

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
  const names = useMemo(() => (catalogue.data ?? []).map((f) => f.name), [catalogue.data]);
  const values = useFeatureValues(symbol, names);
  const start = values.session ? addDays(values.session, -HISTORY_DAYS) : null;
  const tracked = useMemo(() => historyNames(catalogue.data ?? []), [catalogue.data]);
  const history = useFeatureHistory(symbol, tracked, start, values.session);
  const rows = useMemo(
    () => featureRows(catalogue.data ?? [], values.values, history),
    [catalogue.data, values.values, history],
  );
  const shown = useMemo(() => filterRows(rows, query), [rows, query]);
  const columns = useMemo(() => featureColumns(symbol), [symbol]);
  const chosen = rows.find((r) => r.feature.name === feature);
  const failed = catalogue.isError || values.isError;
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
          void values.refetch();
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
          status={catalogue.isPending || values.isPending ? 'loading' : 'ready'}
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
