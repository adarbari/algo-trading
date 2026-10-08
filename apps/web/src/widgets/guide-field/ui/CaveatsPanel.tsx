/**
 * When the number lies: the guide's caveats, the fields they name linked to their pages, in the
 * warning tint, then the situations that fool it, each linked to its page (the server picks
 * them; ADR 0038). A field with neither says so in one line.
 */
import { Banner, Stack, Text, TextLink } from '@algotrade/ui';

import { GuideProse, situationPath, type GuideProseValue } from '@/entities/guide';

export interface CaveatsPanelProps {
  /** The caveats, split at the field names they mention. */
  caveats: readonly GuideProseValue[];
  /** The situations that fool the field: how each shows itself. */
  situations: readonly { name: string; slug: string; signsLinked: GuideProseValue }[];
}

export function CaveatsPanel({ caveats, situations }: CaveatsPanelProps) {
  if (caveats.length === 0 && situations.length === 0) {
    return (
      <Text size="sm" tone="muted">
        The guide lists no caveat for this field yet.
      </Text>
    );
  }
  return (
    <Banner tone="warning" title="When it lies">
      <Stack gap={2}>
        {caveats.map((caveat) => (
          <Text key={caveat.segments.map((s) => s.text).join('')} as="p">
            <GuideProse prose={caveat} />
          </Text>
        ))}
        {situations.length > 0 && (
          <Stack gap={1}>
            <Text weight="medium">Situations that fool it</Text>
            {situations.map((situation) => (
              <Text key={situation.slug} as="p" size="sm">
                <TextLink href={situationPath(situation.slug)} size="inherit">
                  {situation.name}
                </TextLink>
                {': '}
                <GuideProse prose={situation.signsLinked} size="sm" />
              </Text>
            ))}
          </Stack>
        )}
      </Stack>
    </Banner>
  );
}
