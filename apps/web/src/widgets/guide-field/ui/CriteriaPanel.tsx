/**
 * Criteria by intent: one card per use in the field guide (the intent, the rule as op value mode
 * tolerance, the note on combining it) with a way to the Screener Builder. The Builder does not
 * take a criterion by URL yet, so "Add to Builder" opens the Builder only.
 */
import { Button, Grid, Mono, Panel, Stack, Surface, Text } from '@algotrade/ui';

import { ruleText, type GuideUse } from '@/entities/feature';

export interface CriteriaPanelProps {
  uses: readonly GuideUse[];
  /** Opens the Screener Builder. */
  onAddToBuilder: () => void;
}

export function CriteriaPanel({ uses, onAddToBuilder }: CriteriaPanelProps) {
  return (
    <Panel
      title="Use it for"
      state={uses.length === 0 ? 'empty' : 'ready'}
      emptyMessage="The field guide gives no criterion for this field yet."
    >
      <Grid columns={2} gap={3} collapse="md">
        {uses.map((use) => (
          <Surface key={use.intent} tone="row" radius="lg" padding={3}>
            <Stack gap={2}>
              <Text weight="medium">{use.intent}</Text>
              <Mono size="sm">{ruleText(use)}</Mono>
              <Text size="sm" tone="muted">
                {use.note}
              </Text>
              <Stack direction="row">
                <Button size="sm" variant="ghost" onClick={onAddToBuilder}>
                  Add to Builder
                </Button>
              </Stack>
            </Stack>
          </Surface>
        ))}
      </Grid>
    </Panel>
  );
}
