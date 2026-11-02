/**
 * One idea's page: the name under the setup that picked it (a switch when several did), then the
 * sections in the order a trader reads them: why it is here, the setup's historical exit rule,
 * the evidence, what could go wrong and the setup to learn. The sections are the server's
 * (`idea`); a name no setup picked for the session says so and links back to Ideas.
 */
import { Button, Heading, Panel, SegmentedControl, Stack, Text } from '@algotrade/ui';

import { useIdeaDetail } from '@/entities/idea';
import { termHelp } from '@/features/guide-help';

import {
  EvidenceSection,
  ExitRuleSection,
  LearnSection,
  RisksSection,
  WhySection,
} from './IdeaSections';

export interface IdeaDetailProps {
  /** The ticker in the URL. */
  symbol: string;
  /** The setup in the URL (absent: the best that picked it). */
  setup: string | undefined;
  onSetupChange: (edgeId: string) => void;
  /** Open a setup's page. */
  onOpenEdge: (edgeId: string) => void;
  /** Open the name in Explore. */
  onOpenTicker: (symbol: string) => void;
  /** Back to the Ideas list (its tab). */
  onBack: (tab: string) => void;
}

export function IdeaDetail({
  symbol,
  setup,
  onSetupChange,
  onOpenEdge,
  onOpenTicker,
  onBack,
}: IdeaDetailProps) {
  const found = useIdeaDetail(symbol, setup);
  const idea = found.data;
  if (found.isPending || found.isError || !idea) {
    return (
      <Panel
        title={symbol}
        actions={termHelp('idea_why')}
        state={found.isPending ? 'loading' : found.isError ? 'error' : 'empty'}
        loadingLabel="Loading the idea…"
        errorMessage="The idea failed to load."
        emptyMessage={
          <Stack gap={2} align="start">
            <Text tone="muted">No setup picked this name for this session.</Text>
            <Button
              variant="primary"
              onClick={() => {
                onBack('stocks');
              }}
            >
              Back to Ideas
            </Button>
          </Stack>
        }
        onRetry={() => void found.refetch()}
      />
    );
  }
  const shown = idea.symbol ?? idea.instrumentId;
  return (
    <Stack gap={3}>
      <Stack gap={2}>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            onBack(idea.tab);
          }}
        >
          Back to Ideas
        </Button>
        <Heading level={1}>{idea.name ? `${shown} · ${idea.name}` : shown}</Heading>
        {idea.setups.length > 1 ? (
          <SegmentedControl
            aria-label="Setup"
            options={idea.setups.map((s) => ({ value: s.edgeId, label: s.edgeName }))}
            value={idea.setup.edgeId}
            onValueChange={onSetupChange}
          />
        ) : null}
        <Stack direction="row" gap={2} wrap>
          <Button
            variant="secondary"
            onClick={() => {
              onOpenTicker(shown);
            }}
          >
            {`Open ${shown} in Explore`}
          </Button>
        </Stack>
      </Stack>
      <WhySection idea={idea} />
      <ExitRuleSection idea={idea} />
      <EvidenceSection idea={idea} />
      <RisksSection idea={idea} />
      <LearnSection idea={idea} onOpenEdge={onOpenEdge} />
    </Stack>
  );
}
