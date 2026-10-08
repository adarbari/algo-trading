/**
 * "Paused by regime (n)" under the Ideas strip: the picks the regime gate held back today (a
 * screener that pauses in the session's label), listed apart from the ideas with the screener
 * and the reason each run stored, collapsed but never hidden while there are any. The count and
 * the list are the server's (`pausedTotal`, the first rows); with the gate off nothing is
 * paused and the section is not shown.
 */
import { Button, Disclosure, Stack, Text } from '@algotrade/ui';

import { useIdeas, type PausedIdea } from '@/entities/idea';

export interface PausedIdeasProps {
  /** Open one ticker in Explore, with the screener that paused it. */
  onOpen: (symbol: string, via: string) => void;
  /** Open the screener that paused a pick (its name). */
  onOpenScreener: (screenerId: string) => void;
}

function PausedRow({ idea, onOpen, onOpenScreener }: { idea: PausedIdea } & PausedIdeasProps) {
  const { symbol } = idea;
  return (
    <Stack direction="row" gap={2} align="center" wrap>
      {symbol ? (
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            onOpen(symbol, idea.screenerId);
          }}
        >
          {symbol}
        </Button>
      ) : (
        <Text size="sm">{idea.instrumentId}</Text>
      )}
      <Button
        size="sm"
        variant="ghost"
        onClick={() => {
          onOpenScreener(idea.screenerId);
        }}
      >
        {idea.screenerName}
      </Button>
      <Text size="sm" tone="muted">
        {idea.reason || 'Paused by the regime gate'}
      </Text>
    </Stack>
  );
}

export function PausedIdeas({ onOpen, onOpenScreener }: PausedIdeasProps) {
  const ideas = useIdeas();
  if (ideas.isError && !ideas.data) {
    return (
      <Text size="sm" tone="muted">
        The ideas paused by the regime could not be read.
      </Text>
    );
  }
  const data = ideas.data;
  if (!data || data.pausedTotal === 0) return null;
  const hidden = data.pausedTotal - data.paused.length;
  return (
    <Disclosure
      label="Paused by regime"
      count={`(${String(data.pausedTotal)})`}
      countTone="warning"
    >
      <Stack gap={2}>
        <Text size="sm" tone="secondary">
          The regime gate held these picks back for the session. They are not ideas; the reason is
          the rule that paused them.
        </Text>
        {data.paused.map((idea) => (
          <PausedRow
            key={`${idea.screenerId}:${idea.instrumentId}`}
            idea={idea}
            onOpen={onOpen}
            onOpenScreener={onOpenScreener}
          />
        ))}
        {hidden > 0 ? (
          <Text size="sm" tone="muted">{`${String(hidden)} more not listed here`}</Text>
        ) : null}
      </Stack>
    </Disclosure>
  );
}
