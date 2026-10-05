/**
 * A preview row's score as a button; clicking it opens how the score was worked out: 100 minus
 * each missed criterion's penalty (worst first, with why), clipped to 0..100. The caller names
 * the criteria (`labelOf`: the catalogue label of its field), so this entity needs no catalogue.
 */
import { Button, KeyValue, Popover, Stack, Text } from '@algotrade/ui';

import type { PreviewRow } from '../model/preview';
import { FULL_SCORE, scoreBreakdown } from '../model/score';

export interface ScoreBreakdownProps {
  row: PreviewRow;
  /** The criterion's display name (default: its id). */
  labelOf?: (criterionId: string, field: string) => string;
}

const points = (n: number): string => (Number.isInteger(n) ? String(n) : n.toFixed(1));

export function ScoreBreakdown({ row, labelOf = (id) => id }: ScoreBreakdownProps) {
  const breakdown = scoreBreakdown(row);
  const shown = breakdown.score === null ? '–' : points(Math.round(breakdown.score));
  const symbol = row.symbol ?? row.instrument_id;
  const summary = breakdown.lines.length
    ? `${String(FULL_SCORE)} − ${points(breakdown.penalties)} in penalties${breakdown.clipped ? ', clipped to 0' : ''}`
    : `Every criterion passed: the full ${String(FULL_SCORE)}.`;
  return (
    <Popover
      label={`How ${symbol} scored ${shown}`}
      placement="bottom-end"
      trigger={(props) => (
        <Button
          {...props}
          variant="ghost"
          size="sm"
          aria-label={`Score ${shown}: how it was worked out`}
        >
          {shown}
        </Button>
      )}
    >
      <Stack gap={2}>
        <Text weight="semibold">{`${symbol} scored ${shown}`}</Text>
        <Text size="sm" tone="muted">
          {summary}
        </Text>
        {breakdown.lines.length > 0 && (
          <KeyValue
            label="Penalties"
            alignValues="end"
            items={breakdown.lines.map((line) => ({
              id: line.criterionId,
              label: labelOf(line.criterionId, line.field),
              hint: line.why,
              value: `−${points(line.penalty)}`,
            }))}
          />
        )}
        {breakdown.passed > 0 && (
          <Text size="sm" tone="muted">
            {`${String(breakdown.passed)} ${breakdown.passed === 1 ? 'criterion' : 'criteria'} passed with no penalty.`}
          </Text>
        )}
      </Stack>
    </Popover>
  );
}
