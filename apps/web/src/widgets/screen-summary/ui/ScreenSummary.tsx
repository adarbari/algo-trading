/**
 * The preview's run summary: how many rows passed, how many were skipped and why (missing data
 * never passes), the decision counts and the narrow misses (rows that missed only within a
 * tolerance, with the rule and the distance).
 */
import { Banner, Disclosure, KeyValue, Panel, Stack, StatStrip, Text } from '@algotrade/ui';

import { previewPanelState, useScreenerBuilder } from '@/features/screener-builder';
import {
  decisionCounts,
  narrowMissGroups,
  ScreenDecisionBadge,
  type ScreenPreview,
} from '@/entities/screen';

import { missText } from '../model/summary';

const SHOWN_PER_CRITERION = 5;

function Summary({ preview }: { preview: ScreenPreview }) {
  const { summary, coverage } = preview;
  const symbols = new Map(preview.rows.map((row) => [row.instrument_id, row.symbol]));
  const groups = narrowMissGroups(summary.narrow_misses);
  const reasons = Object.entries(summary.skipped_reasons).sort((a, b) => b[1] - a[1]);
  return (
    <Stack gap={3}>
      <StatStrip
        label="Run totals"
        items={[
          { label: 'Screened', value: coverage.selected, format: { kind: 'number' } },
          { label: 'Passed', value: summary.passed, format: { kind: 'number' }, tone: 'positive' },
          {
            label: 'Skipped',
            value: summary.skipped,
            format: { kind: 'number' },
            sub: 'data missing',
          },
          {
            label: 'Coverage',
            value: coverage.coverage_pct,
            format: { kind: 'percent' },
            sub: coverage.coverage,
          },
        ]}
      />
      <Stack direction="row" gap={3} align="center" wrap>
        {decisionCounts(preview).map(({ decision, count }) => (
          <Stack key={decision} direction="row" gap={1} align="center">
            <ScreenDecisionBadge decision={decision} />
            <Text size="sm" numeric>
              {count.toLocaleString('en-US')}
            </Text>
          </Stack>
        ))}
      </Stack>
      {coverage.coverage !== 'COMPLETE' && (
        <Banner
          tone="warning"
          title={`Coverage: ${coverage.coverage.toLowerCase().replace(/_/g, ' ')}`}
        >
          {coverage.missing_tables.length > 0
            ? `No rows stored for ${coverage.missing_tables.join(', ')} on ${preview.session}.`
            : 'Some rows could not be evaluated.'}
        </Banner>
      )}
      {reasons.length > 0 && (
        <Disclosure
          label="Skipped"
          count={summary.skipped.toLocaleString('en-US')}
          countTone="warning"
        >
          <KeyValue
            label="Skipped by reason"
            items={reasons.map(([reason, n]) => ({
              label: reason,
              value: n.toLocaleString('en-US'),
            }))}
          />
        </Disclosure>
      )}
      {groups.length > 0 && (
        <Disclosure
          label="Narrow misses"
          count={summary.narrow_misses.length.toLocaleString('en-US')}
        >
          <Stack gap={2}>
            {groups.map((group) => (
              <Stack gap={1} key={group.criterionId}>
                <Text
                  size="sm"
                  weight="medium"
                >{`${group.criterionId} (${String(group.misses.length)})`}</Text>
                {group.misses.slice(0, SHOWN_PER_CRITERION).map((miss) => (
                  <Text size="sm" tone="secondary" key={miss.instrument_id} mono>
                    {missText(miss, symbols.get(miss.instrument_id) ?? null)}
                  </Text>
                ))}
              </Stack>
            ))}
          </Stack>
        </Disclosure>
      )}
    </Stack>
  );
}

export function ScreenSummary() {
  const { preview } = useScreenerBuilder();
  const state = previewPanelState(preview);
  return (
    <Panel
      title="Run summary"
      description={preview.data ? `Session ${preview.data.session}` : undefined}
      state={state}
      loadingLabel="Running the preview…"
      emptyMessage="Add a complete criterion to see the run summary."
      errorMessage={preview.error ?? 'The preview failed.'}
    >
      {preview.data && <Summary preview={preview.data} />}
    </Panel>
  );
}
