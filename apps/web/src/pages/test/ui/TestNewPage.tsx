/**
 * Test > Expert or Describe it, step one: name a screener and its blank draft opens in the Builder
 * (Expert's rules, with the Describe it box on top for the sentence way in).
 */
import { Heading, Panel, Stack, Text } from '@algotrade/ui';

import { NewScreenerForm } from '@/features/screener-builder';
import { termHelp } from '@/features/guide-help';

import { TestSteps } from './TestSteps';

export interface TestNewPageProps {
  /** Which way in this is. */
  way: 'expert' | 'describe';
  /** The draft was created: open it in the Builder. */
  onCreated: (id: string) => void;
  /** Back to the start. */
  onCancel: () => void;
}

export function TestNewPage({ way, onCreated, onCancel }: TestNewPageProps) {
  const describe = way === 'describe';
  return (
    <Stack gap={3}>
      <TestSteps at={way} />
      <Stack direction="row" gap={1} align="center">
        <Heading level={1}>{describe ? 'Describe it' : 'Expert'}</Heading>
        {termHelp(describe ? 'test_describe' : 'test_expert')}
      </Stack>
      <Text size="sm" tone="secondary">
        Name your screener.
      </Text>
      <Panel title="Name and universe">
        <NewScreenerForm onCreated={onCreated} onCancel={onCancel} />
      </Panel>
    </Stack>
  );
}
