/**
 * The "Proposed formulas" group of the review: each formula the draft offers as a FormulaPreview
 * (the formula, its inputs and unit, the server's dry run, five sample rows) with Review and add /
 * Skip. The decision lives in the Builder (`formulaStates`): a decided formula shows its state
 * and no buttons. The formula flow itself (the review dialog, the pending row) is the owner's.
 */
import { Button, FormulaPreview, Panel, Stack, StatusBadge, Text } from '@algotrade/ui';

import { GuideHelp, termHelp } from '@/features/guide-help';
import type { FormulaState } from '@/features/screener-builder';
import { dryRunStats, inputsLine, sampleOf, type DraftFormula } from '@/features/screener-describe';

export interface ProposedFormulasProps {
  formulas: readonly DraftFormula[];
  states: Readonly<Record<string, FormulaState>>;
  onReview: (formula: DraftFormula) => void;
  onSkip: (name: string) => void;
}

function StateBadge({ state }: { state: FormulaState }) {
  if (state === 'accepted') return <StatusBadge tone="positive">Accepted</StatusBadge>;
  if (state === 'skipped') return <StatusBadge tone="neutral">Skipped</StatusBadge>;
  return (
    <Stack direction="row" gap={1} align="center">
      <StatusBadge tone="info">Pending formula</StatusBadge>
      <GuideHelp entry={{ kind: 'term', id: 'describe_pending_formula' }} />
    </Stack>
  );
}

export function ProposedFormulas({ formulas, states, onReview, onSkip }: ProposedFormulasProps) {
  return (
    <Panel
      title="Proposed formulas"
      description="Nothing is added until you review it"
      headingLevel={3}
      actions={termHelp('describe_proposed_formulas')}
    >
      <Stack gap={4}>
        {formulas.map((formula) => {
          const state = states[formula.name] ?? 'proposed';
          return (
            <Stack key={formula.name} gap={2}>
              <Stack direction="row" gap={2} align="center" wrap>
                <StateBadge state={state} />
                <Text size="sm" tone="muted">
                  {formula.description}
                </Text>
              </Stack>
              <FormulaPreview
                name={formula.name}
                formula={formula.expr}
                inputs={inputsLine(formula)}
                stats={dryRunStats(formula)}
                statsLabel={`Dry run of ${formula.name}`}
                sample={sampleOf(formula)}
                actions={
                  state === 'proposed' ? (
                    <>
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={() => {
                          onReview(formula);
                        }}
                      >
                        Review and add
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          onSkip(formula.name);
                        }}
                      >
                        Skip
                      </Button>
                    </>
                  ) : undefined
                }
              />
            </Stack>
          );
        })}
      </Stack>
    </Panel>
  );
}
