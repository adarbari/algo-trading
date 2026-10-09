/**
 * How the edge is defined, in six parts (idea, screens, picks, trade, what it is compared
 * against, the test), and why it should last with its sources: each source a link when its
 * document has a url, plain text otherwise. The sentences are the read model's.
 */
import {
  ExternalLink,
  KeyValue,
  Panel,
  Stack,
  Text,
  TextLink,
  type KeyValueItem,
} from '@algotrade/ui';

import type { Edge } from '@/entities/edge';

export interface EdgeDefinitionProps {
  edge: Edge;
}

function parts(edge: Edge): KeyValueItem[] {
  const d = edge.definition;
  return [
    { id: 'idea', label: '1 · Idea', value: edge.thesis },
    {
      id: 'screens',
      label: '2 · Screens',
      value:
        edge.screeners.length === 0 ? (
          'No screen yet'
        ) : (
          <Stack gap={0}>
            {edge.screeners.map((id) => (
              <TextLink key={id} href={`/screeners/${id}`} mono size="sm">
                {id}
              </TextLink>
            ))}
          </Stack>
        ),
    },
    { id: 'picks', label: '3 · Picks', value: d.picks },
    { id: 'trade', label: '4 · Trade', value: d.trade },
    { id: 'compare', label: '5 · Compare against', value: d.compare },
    { id: 'test', label: '6 · Test', value: d.test },
  ];
}

export function EdgeDefinition({ edge }: EdgeDefinitionProps) {
  return (
    <Stack gap={3}>
      <Panel title="How the edge is defined">
        <KeyValue label={`${edge.name} definition`} items={parts(edge)} />
      </Panel>
      <Panel title="Why it should last">
        <Stack gap={2}>
          <Text size="sm">{edge.persistence}</Text>
          {edge.sources.length > 0 && (
            <Stack gap={0}>
              {edge.sources.map((s) =>
                s.url ? (
                  <ExternalLink key={s.title} href={s.url} size="sm">
                    {s.title}
                  </ExternalLink>
                ) : (
                  <Text key={s.title} size="sm" tone="secondary">
                    {s.title}
                  </Text>
                ),
              )}
            </Stack>
          )}
        </Stack>
      </Panel>
    </Stack>
  );
}
