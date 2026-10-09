/**
 * Robustness: the edge's out-of-sample lift (a marker) among the lifts of the random-pick
 * backtests (a `Distribution`), with the server's sentence under it (the share beaten and the
 * variants tried). The bins, the share and the sentence are served; a run that drew none shows
 * an empty panel.
 */
import { Distribution, Panel, Stack, Text } from '@algotrade/ui';

import type { EdgeVerdict } from '@/entities/edge';
import { GuideHelp } from '@/features/guide-help';

export interface EdgeRobustnessProps {
  robustness: EdgeVerdict['robustness'];
}

export function EdgeRobustness({ robustness }: EdgeRobustnessProps) {
  return (
    <Panel
      title="Robustness"
      state={robustness ? 'ready' : 'empty'}
      emptyMessage="No random-pick backtests for this result."
      actions={<GuideHelp entry={{ kind: 'term', id: 'robustness' }} />}
    >
      {robustness && (
        <Stack gap={2}>
          <Distribution
            label="Lift of random-pick backtests"
            bins={robustness.bins}
            format={{ kind: 'number', digits: 2 }}
            markers={[{ value: robustness.lift, label: 'This edge', tone: 'accent' }]}
          />
          <Text size="sm">{robustness.summary}</Text>
        </Stack>
      )}
    </Panel>
  );
}
