/**
 * Section "Before you act" of a setup's page: the checks that apply to any setup, as a checklist.
 * What each check means is in the Guide entry on the section's help button.
 */
import { Heading, ProseList, Stack, type ProseListItem } from '@algotrade/ui';

import { termHelp } from '@/features/guide-help';

const CHECKS: ProseListItem[] = [
  { id: 'report', body: 'Check the next report date: a report inside the hold changes the bet' },
  { id: 'stop', body: "The stop is the setup's history, not a fit to any account" },
  { id: 'basis', body: 'Backtests are hypothetical; capital is at risk' },
];

export function BeforeYouAct() {
  return (
    <Stack gap={2}>
      <Stack direction="row" gap={1} align="center">
        <Heading level={2}>Before you act</Heading>
        {termHelp('setup_before_you_act')}
      </Stack>
      <ProseList marker="box" items={CHECKS} aria-label="Before you act" />
    </Stack>
  );
}
