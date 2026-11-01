/**
 * Section "The rules" of a setup's page: the idea, the screens that find it, how it picks and how
 * it trades (the historical exit rule), as a label / value grid; and behind a disclosure what it
 * is compared against, how it is tested and why it should last, with its sources: each a link
 * when its document has a url, plain text otherwise. The sentences are the read model's.
 */
import {
  Disclosure,
  ExternalLink,
  Heading,
  KeyValue,
  Stack,
  Text,
  TextLink,
  type KeyValueItem,
} from '@algotrade/ui';

import type { Edge } from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

export interface SetupRulesProps {
  edge: Edge;
}

function rules(edge: Edge): KeyValueItem[] {
  const d = edge.definition;
  return [
    { id: 'idea', label: 'Idea', value: edge.thesis },
    {
      id: 'screens',
      label: 'Screens',
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
    { id: 'picks', label: 'Picks', value: d.picks },
    { id: 'trade', label: 'Historical exit rule', value: d.trade },
  ];
}

export function SetupRules({ edge }: SetupRulesProps) {
  const d = edge.definition;
  return (
    <Stack gap={3}>
      <Stack direction="row" gap={1} align="center">
        <Heading level={2}>The rules</Heading>
        {termHelp('edge_definition')}
      </Stack>
      <KeyValue layout="grid" label={`${edge.name} rules`} items={rules(edge)} />
      <Disclosure label="Compared against, tested, and why it should last">
        <Stack gap={3}>
          <KeyValue
            layout="grid"
            label={`${edge.name} test`}
            items={[
              { id: 'compare', label: 'Compared against', value: d.compare },
              { id: 'test', label: 'Test', value: d.test },
              {
                id: 'persistence',
                label: 'Why it should last',
                action: termHelp('edge_persistence'),
                value: edge.persistence,
              },
            ]}
          />
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
      </Disclosure>
    </Stack>
  );
}
