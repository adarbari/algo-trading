/**
 * "Ideas for Fri 2 Oct": the session the stored lists are for; plain "Ideas" while loading or
 * when nothing is stored. Under it, the Stocks | Premium tabs (the page's `tab` search param).
 */
import { formatValue, Heading, SegmentedControl, Stack } from '@algotrade/ui';

import { IDEA_TABS, useSetupIdeas, type IdeaTab } from '@/entities/idea';
import { termHelp } from '@/features/guide-help';

export interface IdeasHeadingProps {
  tab: IdeaTab;
  onTabChange: (tab: IdeaTab) => void;
}

export function IdeasHeading({ tab, onTabChange }: IdeasHeadingProps) {
  const session = useSetupIdeas(tab).data?.session;
  return (
    <Stack gap={2}>
      <Heading level={1}>
        {session
          ? `Ideas for ${formatValue(session, { kind: 'date', style: 'weekday' }).text}`
          : 'Ideas'}
      </Heading>
      <Stack direction="row" gap={2} align="center">
        <SegmentedControl
          aria-label="Ideas tab"
          options={IDEA_TABS.map((t) => ({ value: t.id, label: t.label }))}
          value={tab}
          onValueChange={onTabChange}
        />
        {termHelp('idea_tab')}
      </Stack>
    </Stack>
  );
}
