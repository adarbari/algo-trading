/**
 * Test > Start: the four ways in (Guided, Expert, Describe it, and one of yours below), then the
 * list of your screeners and the site's templates. Everything after it is the same flow: build the
 * rules, read the result.
 */
import { Heading, OptionList, Stack, Text } from '@algotrade/ui';

import { termHelp } from '@/features/guide-help';
import {
  ScreenerList,
  type ScreenerListSearch,
  type ScreenerListSearchPatch,
} from '@/widgets/screener-list';

import { TestSteps } from './TestSteps';

/** The ways in that open a page of their own (the fourth is the list under the cards). */
export type TestWay = 'guided' | 'expert' | 'describe';

const WAYS = [
  { id: 'guided', title: 'Guided', description: 'Start from a template and change what you like.' },
  { id: 'expert', title: 'Expert', description: 'Write the rules yourself, field by field.' },
  {
    id: 'describe',
    title: 'Describe it',
    description: 'Say it in a sentence and review the rules.',
  },
] as const;

export interface TestStartPageProps {
  /** A way in was chosen. */
  onChoose: (way: TestWay) => void;
  /** Open a screener's result. */
  onOpen: (id: string) => void;
  /** Open a screener's rules (Expert). */
  onEdit: (id: string) => void;
  /** Open an edge's evidence. */
  onOpenEdge: (edgeId: string) => void;
  /** The list's filters and search (from the URL) and their change. */
  search: ScreenerListSearch;
  onSearchChange: (patch: ScreenerListSearchPatch) => void;
}

export function TestStartPage({
  onChoose,
  onOpen,
  onEdit,
  onOpenEdge,
  search,
  onSearchChange,
}: TestStartPageProps) {
  return (
    <Stack gap={3}>
      <TestSteps at="start" />
      <Stack gap={1}>
        <Stack direction="row" gap={1} align="center">
          <Heading level={1}>Test</Heading>
          {termHelp('test_flow')}
        </Stack>
        <Text size="sm" tone="secondary">
          Pick a way in.
        </Text>
      </Stack>
      <OptionList
        variant="card"
        label="Ways in"
        items={WAYS}
        value={null}
        onSelect={(id) => {
          onChoose(id as TestWay);
        }}
      />
      <Stack gap={2}>
        <Stack direction="row" gap={1} align="center">
          <Heading level={2}>Yours and the site's</Heading>
          {termHelp('test_yours')}
        </Stack>
        <ScreenerList
          search={search}
          onSearchChange={onSearchChange}
          onOpen={onOpen}
          onEdit={onEdit}
          onOpenEdge={onOpenEdge}
        />
      </Stack>
    </Stack>
  );
}
