/**
 * The "Run backtest" button of an edge: evaluates it now under the user's own split (rows are
 * theirs; an out-of-sample date other than the official one is EXPLORATORY), shows the job's state, and an admin
 * also gets "Run as site". The API's refusal (another evaluation running, no outcomes stored) is
 * the message.
 */
import { Button, Stack, Text } from '@algotrade/ui';

import { useViewer } from '@/entities/viewer';
import { errorDetail } from '@/shared/api';

import { useRunEvaluation } from '../api/hooks';
import { evaluationMessage } from '../model/evaluation';

export interface RunEvaluationProps {
  /** The edge to evaluate. */
  edgeId: string;
}

export function RunEvaluation({ edgeId }: RunEvaluationProps) {
  const runner = useRunEvaluation(edgeId);
  const viewer = useViewer();
  const admin = viewer.data?.role === 'admin';
  const message = runner.error ? errorDetail(runner.error) : evaluationMessage(runner.run);
  return (
    <Stack direction="row" gap={2} align="center" wrap>
      <Button
        size="sm"
        variant="primary"
        loading={runner.running}
        onClick={() => {
          runner.start(false);
        }}
      >
        Run backtest
      </Button>
      {admin && (
        <Button
          size="sm"
          variant="secondary"
          disabled={runner.running}
          onClick={() => {
            runner.start(true);
          }}
        >
          Run as site
        </Button>
      )}
      {message && (
        <Text size="sm" tone="muted">
          {message}
        </Text>
      )}
    </Stack>
  );
}
