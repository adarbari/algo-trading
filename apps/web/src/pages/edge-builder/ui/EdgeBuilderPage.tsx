/**
 * Trader > Edges > the builder: the six-step form, and after "Save and run backtest" the running
 * backtest (the existing evaluation job: the user may leave, the result lands on the edge page).
 */
import { Banner, Button, Heading, Panel, Stack, StatusBadge, Text } from '@algotrade/ui';
import { useEffect, useRef, useState } from 'react';

import { errorDetail } from '@/shared/api';
import { EdgeBuilder, HelpProvider } from '@/features/edge-builder';
import { evaluationMessage, useRunEvaluation } from '@/features/edge-evaluation';
import { GuideHelp } from '@/features/guide-help';

export interface EdgeBuilderPageProps {
  /** The edge to build or change; null: a new one. */
  id: string | null;
  /** A screen to add to the edge (back from the Screen Builder). */
  addScreen?: string | undefined;
  /** Open the Screen Builder on a screen (null: a new one). */
  onOpenScreen: (id: string | null, from: string | null) => void;
  /** Leave the builder without saving. */
  onCancel: () => void;
  /** Open the edge's page. */
  onOpenEdge: (id: string) => void;
}

const help = (term: string) => <GuideHelp entry={{ kind: 'term', id: term }} />;

export function EdgeBuilderPage({
  id,
  addScreen,
  onOpenScreen,
  onCancel,
  onOpenEdge,
}: EdgeBuilderPageProps) {
  const [running, setRunning] = useState<string | null>(null);
  if (running !== null) return <Running edgeId={running} onOpenEdge={onOpenEdge} />;
  return (
    <HelpProvider value={help}>
      <EdgeBuilder
        id={id}
        addScreen={addScreen}
        onCancel={onCancel}
        onOpenScreen={(screen) => {
          onOpenScreen(screen, id);
        }}
        onSaved={(saved, run) => {
          if (run) setRunning(saved);
          else onOpenEdge(saved);
        }}
      />
    </HelpProvider>
  );
}

/** "Backtest running": starts the evaluation once and follows the job. */
function Running({ edgeId, onOpenEdge }: { edgeId: string; onOpenEdge: (id: string) => void }) {
  const runner = useRunEvaluation(edgeId);
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    runner.start(false);
  }, [runner]);
  const message = runner.error ? errorDetail(runner.error) : evaluationMessage(runner.run);
  return (
    <Stack gap={3}>
      <Stack direction="row" gap={2} align="baseline" wrap>
        <Heading level={1}>{edgeId}</Heading>
        <StatusBadge tone={runner.running ? 'info' : runner.error ? 'negative' : 'positive'}>
          {runner.running ? 'Backtest running' : 'Backtest finished'}
        </StatusBadge>
      </Stack>
      <Panel title="Backtest" actions={help('edge_builder_running')}>
        <Stack gap={2}>
          {runner.error && (
            <Banner tone="negative" title="The backtest did not start">
              {message}
            </Banner>
          )}
          {!runner.error && message && <Text size="sm">{message}</Text>}
          <Stack direction="row" gap={2}>
            <Button
              variant="primary"
              onClick={() => {
                onOpenEdge(edgeId);
              }}
            >
              {runner.running ? 'Open the edge' : 'Show result'}
            </Button>
          </Stack>
        </Stack>
      </Panel>
    </Stack>
  );
}
