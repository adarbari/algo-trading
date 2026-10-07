/**
 * The Guide's home: one block per section that has pages today, in the spec's order (sections of
 * later phases stay out). Each block is the section's title and purpose as the server gives
 * them; Fields lists the theme groups in the order a screen uses them, with the field count of
 * every theme, and links to the by-intent and A to Z views.
 */
import {
  EmptyState,
  ErrorState,
  Grid,
  Heading,
  Skeleton,
  Stack,
  Text,
  TextLink,
} from '@algotrade/ui';

import { BUILT_SECTIONS, fieldsPath, themeTitle, useGuideIndex } from '@/entities/guide';

export function GuideHome() {
  const index = useGuideIndex();
  if (index.isError) {
    return <ErrorState title="The Guide failed to load." onRetry={() => void index.refetch()} />;
  }
  if (index.isPending) return <Skeleton variant="rect" height="lg" label="Loading the Guide" />;
  if (!index.data) return <EmptyState bordered title="The Guide has no entries." />;
  const { sections, themeGroups } = index.data;
  return (
    <Stack gap={6}>
      <Stack gap={1}>
        <Heading level={1} size="3xl">
          Guide
        </Heading>
        <Text as="p" tone="secondary">
          What each number in the app means, how to read it and when it misleads.
        </Text>
      </Stack>
      {sections
        .filter((s) => BUILT_SECTIONS.includes(s.id))
        .map((section) => (
          <Stack key={section.id} gap={3} as="section" aria-label={section.title}>
            <Stack direction="row" gap={3} align="baseline" wrap>
              <Heading level={2} size="2xl">
                {section.title}
              </Heading>
              <Text tone="muted">{`${section.entries.toLocaleString('en-US')} entries`}</Text>
              <Stack direction="row" gap={3}>
                <TextLink href={fieldsPath({ view: 'intent' })} size="sm">
                  By intent
                </TextLink>
                <TextLink href={fieldsPath({ view: 'az' })} size="sm">
                  A to Z
                </TextLink>
              </Stack>
            </Stack>
            <Text as="p" tone="secondary">
              {section.purpose}
            </Text>
            <Grid columns={2} gap={5} collapse="md" align="start">
              {themeGroups.map((group) => (
                <Stack key={group.id} gap={2} as="section" aria-label={group.title}>
                  <Heading level={3} tone="muted">
                    {group.title}
                  </Heading>
                  {group.themes.map((t) => (
                    <TextLink key={t.theme} href={fieldsPath({ theme: t.theme })}>
                      {`${themeTitle(t.theme)} · ${String(t.fields)}`}
                    </TextLink>
                  ))}
                </Stack>
              ))}
            </Grid>
          </Stack>
        ))}
    </Stack>
  );
}
