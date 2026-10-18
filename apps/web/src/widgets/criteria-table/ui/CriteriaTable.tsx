/**
 * The Builder's criteria: the screen read back in plain English, then one row per criterion
 * (mode, feature with its help drawer, operator, threshold, tolerance, distribution), add a criterion or a formula
 * feature, the tie-break column, and the universe it runs over.
 */
import { Button, Divider, EmptyState, Legend, Panel, PendingRow, Stack, Text } from '@algotrade/ui';
import { useState } from 'react';

import { useFeatureCatalogue } from '@/entities/feature';
import { TieBreakField, useScreenerBuilder } from '@/features/screener-builder';
import { FormulaFeatureDialog } from '@/features/formula-feature';
import { termHelp } from '@/features/guide-help';

import { CriteriaRows } from './CriteriaRows';
import { pendingLine } from '../model/pending';
import { plainEnglish } from '../model/plain-english';

const LEGEND = [
  { label: 'Hard: must pass', tone: 'accent' as const },
  { label: 'Soft: near miss tolerated', tone: 'info' as const },
  { label: 'Score: only ranks', tone: 'muted' as const },
];

export function CriteriaTable() {
  const builder = useScreenerBuilder();
  const catalogue = useFeatureCatalogue();
  const [formula, setFormula] = useState(false);
  const features = catalogue.data ?? [];
  const sentence = plainEnglish(builder.criteria, features, builder.notes, builder.groups);
  const waiting = builder.pendingFormulas.flatMap((formula) => {
    const line = pendingLine(formula);
    return line ? [{ formula, line }] : [];
  });
  const state =
    builder.status === 'loading' ? 'loading' : builder.status === 'error' ? 'error' : 'ready';

  return (
    <Stack gap={3}>
      {sentence && (
        <Panel title="In plain English">
          <Text as="p" size="lg">
            {sentence}
          </Text>
        </Panel>
      )}
      <Panel
        title="Criteria"
        state={state}
        loadingLabel="Loading the screener…"
        errorMessage="The screener failed to load."
        onRetry={builder.retry}
        actions={<Legend items={LEGEND} label="Criterion modes" size="sm" />}
        footer="Fields come from the feature catalogue; formulas are saved as your own features."
      >
        <Stack gap={3}>
          {builder.criteria.length === 0 && waiting.length === 0 && (
            <EmptyState
              compact
              title="No criteria yet"
              description="Add a criterion to start; the preview follows as you type."
            />
          )}
          <CriteriaRows nodes={builder.layout} />
          {waiting.map(({ formula, line }) => (
            <PendingRow
              key={formula.name}
              label="Waiting on formula"
              help={termHelp('describe_waiting_on_formula')}
              name={line.name}
              summary={line.summary}
              actions={
                <>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => {
                      builder.reviewFormula(formula);
                    }}
                  >
                    Review and add
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      builder.skipFormula(formula.name);
                    }}
                  >
                    Skip
                  </Button>
                </>
              }
            />
          ))}
          <Stack direction="row" gap={2} align="center" wrap>
            <Button
              variant="dashed"
              onClick={() => {
                builder.addCriterion();
              }}
            >
              + Add criterion
            </Button>
            <Button
              variant="dashed"
              onClick={() => {
                setFormula(true);
              }}
            >
              + Add formula feature
            </Button>
          </Stack>
          <Divider tone="soft" />
          <TieBreakField
            catalogue={features}
            field={builder.tieBreak.field}
            order={builder.tieBreak.order}
            onChange={builder.setTieBreak}
          />
          <Text size="sm" tone="secondary">
            The preview runs on the latest closed session.
          </Text>
        </Stack>
      </Panel>
      <FormulaFeatureDialog
        open={formula}
        onOpenChange={setFormula}
        onSaved={(field) => {
          builder.addCriterion(field);
        }}
      />
    </Stack>
  );
}
