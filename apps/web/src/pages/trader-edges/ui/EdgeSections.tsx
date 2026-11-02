/**
 * Everything below a setup's head, in one chunk (the page lazy-loads it once), in reading order:
 * the rules, how it has done, when it fails, before you act, and Dig deeper (with the trades and
 * the diagnostics inside it). Each section is a `LazySection`, so it renders and reads its data
 * when it nears the viewport; their ids are what the page's navigation scrolls to. An option
 * setup (`Query.edgeOptionSetup`, ADR 0088) swaps its rules and record sections for the option
 * ones; a share setup, and an option setup while its read loads, shows the original.
 */
import { Stack } from '@algotrade/ui';

import { useOptionSetup, type Edge, type LiveState } from '@/entities/edge';
import { EdgeDiagnostics } from '@/widgets/edge-diagnostics';
import { EdgeTrades } from '@/widgets/edge-trades';
import { BeforeYouAct } from '@/widgets/setup-checklist';
import { SetupOptionRecord } from '@/widgets/setup-option-record';
import { SetupOptionRules } from '@/widgets/setup-option-rules';
import { SetupDeeper } from '@/widgets/setup-deeper';
import { SetupFails } from '@/widgets/setup-fails';
import { SetupRecord } from '@/widgets/setup-record';
import { SetupRules } from '@/widgets/setup-rules';

import { EdgeSection } from './EdgeSection';

export interface EdgeSectionsProps {
  edge: Edge;
  /** The setup's live state for the session (its section always shows: a record or why none). */
  live: LiveState | undefined;
}

export function EdgeSections({ edge, live }: EdgeSectionsProps) {
  const option = useOptionSetup(edge.id).data;
  const optionRules = option?.positionKind === 'options' ? option : null;
  const optionEvidence = optionRules?.evidence ?? null;
  return (
    <>
      <EdgeSection id="setup-rules" label="The rules" size="md">
        <Stack gap={4}>
          <SetupRules edge={edge} />
          {optionRules ? <SetupOptionRules name={edge.name} setup={optionRules} /> : null}
        </Stack>
      </EdgeSection>
      <EdgeSection id="setup-record" label="How it has done" size="xl">
        {optionEvidence ? (
          <SetupOptionRecord evidence={optionEvidence} />
        ) : (
          <SetupRecord edgeId={edge.id} verdict={edge.verdict} live={live} />
        )}
      </EdgeSection>
      <EdgeSection id="setup-fails" label="When it fails">
        <SetupFails edgeId={edge.id} />
      </EdgeSection>
      <EdgeSection id="setup-before" label="Before you act" size="sm">
        <BeforeYouAct />
      </EdgeSection>
      <EdgeSection id="setup-deeper" label="Dig deeper" size="sm">
        <SetupDeeper edge={edge}>
          <EdgeTrades edgeId={edge.id} />
          <EdgeDiagnostics edgeId={edge.id} />
        </SetupDeeper>
      </EdgeSection>
    </>
  );
}
