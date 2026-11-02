/**
 * Test > Describe it: one screener's sentence and the rules it became (ADR 0041; Evening Desk
 * CreateDescribe). The Test steps, the draft bar (the screener's name, save, finalise), the sentence box with the
 * sentence as read (C17) and one card per part (C18), then the rows it became (a proposed
 * formula waits there as a pending row until the trader decides). The model only translates the
 * sentence: it never adds a rule (ADR 0083 decision 4). Expert has the preview and the funnel.
 * The widgets share the Builder's state through its provider; save before leaving the page.
 */
import { LinkButton, Stack } from '@algotrade/ui';

import { ScreenerBuilderProvider } from '@/features/screener-builder';
import { CriteriaTable } from '@/widgets/criteria-table';
import { DescribeScreen } from '@/widgets/describe-screen';
import { DraftBar } from '@/widgets/draft-bar';

import { TestSteps } from './TestSteps';

export interface TestDescribePageProps {
  /** The screener being described. */
  id: string;
  /** The screener was deleted: back to the start. */
  onDeleted: () => void;
  /** Open it on Expert (its preview and funnel). */
  onOpenExpert: () => void;
}

export function TestDescribePage({ id, onDeleted, onOpenExpert }: TestDescribePageProps) {
  return (
    <ScreenerBuilderProvider id={id} key={id}>
      <Stack gap={3}>
        <TestSteps at="describe" id={id} />
        <DraftBar onDeleted={onDeleted} />
        <DescribeScreen />
        <CriteriaTable />
        <Stack direction="row" justify="end">
          <LinkButton onClick={onOpenExpert}>Open in Expert</LinkButton>
        </Stack>
      </Stack>
    </ScreenerBuilderProvider>
  );
}
