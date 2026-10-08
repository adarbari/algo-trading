/**
 * "Before you act on a hit": the caveats of the playbook's fields (the field names linked) and,
 * under them, the situations that fool those fields, each a link to its page.
 */
import { Heading, Stack, Text, TextLink } from '@algotrade/ui';

import { GuideProse, situationPath, type GuideProseValue } from '@/entities/guide';

export interface BeforeActingProps {
  caveats: readonly GuideProseValue[];
  situations: readonly { slug: string; name: string }[];
}

export function BeforeActing({ caveats, situations }: BeforeActingProps) {
  if (caveats.length === 0 && situations.length === 0) return null;
  return (
    <Stack gap={2} as="section" aria-label="Before you act on a hit">
      <Heading level={2}>Before you act on a hit</Heading>
      {caveats.length > 0 && (
        <Stack gap={2} as="ul">
          {caveats.map((caveat) => (
            <Stack key={caveat.segments.map((s) => s.text).join('')} as="li" gap={0}>
              <Text as="p">
                <GuideProse prose={caveat} />
              </Text>
            </Stack>
          ))}
        </Stack>
      )}
      {situations.length > 0 && (
        <Stack direction="row" gap={3} wrap align="baseline">
          <Text size="sm" tone="muted">
            Situations that fool its fields:
          </Text>
          {situations.map((s) => (
            <TextLink key={s.slug} href={situationPath(s.slug)} size="sm">
              {s.name}
            </TextLink>
          ))}
        </Stack>
      )}
    </Stack>
  );
}
