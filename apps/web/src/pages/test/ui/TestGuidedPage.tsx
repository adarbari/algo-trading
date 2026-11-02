/**
 * Test > Guided: the site's templates as cards. Picking one opens it in Expert with its rules and
 * live preview; the first change makes a copy that is yours (the Builder does it, pinned to the
 * template's version), so the template itself never changes here.
 */
import { Banner, Heading, OptionList, Stack, Text } from '@algotrade/ui';

import { useScreenerRuns, useScreeners } from '@/entities/screen';
import { termHelp } from '@/features/guide-help';

import { TestSteps } from './TestSteps';

export interface TestGuidedPageProps {
  /** A template was picked: open it. */
  onPick: (id: string) => void;
}

export function TestGuidedPage({ onPick }: TestGuidedPageProps) {
  const configs = useScreeners();
  const runs = useScreenerRuns();
  const items = (configs.data ?? [])
    .filter((c) => c.scope === 'site')
    .map((c) => ({
      id: c.configId,
      title: c.configId,
      description: runs.data?.byId.get(c.configId)?.description ?? '',
    }));
  return (
    <Stack gap={3}>
      <TestSteps at="guided" />
      <Stack direction="row" gap={1} align="center">
        <Heading level={1}>Guided</Heading>
        {termHelp('test_guided')}
      </Stack>
      <Text size="sm" tone="secondary">
        Pick a template.
      </Text>
      {configs.isError ? (
        <Banner tone="negative">The templates did not load.</Banner>
      ) : (
        <OptionList
          variant="card"
          label="Templates"
          items={items}
          value={null}
          loading={configs.isPending}
          emptyMessage="No templates are published."
          onSelect={onPick}
        />
      )}
    </Stack>
  );
}
