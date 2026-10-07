/** Sources: where the field guide's reading comes from, one line each, quiet. */
import { Heading, Stack, Text } from '@algotrade/ui';

export interface SourcesPanelProps {
  sources: readonly string[];
}

export function SourcesPanel({ sources }: SourcesPanelProps) {
  return (
    <Stack gap={1}>
      <Heading level={2}>Sources</Heading>
      {sources.length === 0 ? (
        <Text size="sm" tone="muted">
          The guide cites no source for this field.
        </Text>
      ) : (
        sources.map((source) => (
          <Text key={source} size="sm" tone="muted">
            {source}
          </Text>
        ))
      )}
    </Stack>
  );
}
