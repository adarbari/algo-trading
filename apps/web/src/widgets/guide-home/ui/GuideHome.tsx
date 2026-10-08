/**
 * The Guide's home: one block per section, in the spec's order (Start here first, Glossary
 * last). Start here lists its numbered pages with their summaries, the Glossary its terms. Each block is the section's title and purpose as the server gives
 * them; Market regime lists the warning signs and the market falls, Playbooks lists the families with their playbooks, Fields the theme groups in the order
 * a screen uses them (with the field count of every theme, and links to the by-intent and A to Z
 * views), Situations the situations with how many fields each fools.
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

import {
  BUILT_SECTIONS,
  episodePath,
  fieldsPath,
  GUIDE_GLOSSARY_PATH,
  GUIDE_PLAYBOOKS_PATH,
  GUIDE_REGIME_PATH,
  GUIDE_SITUATIONS_PATH,
  GUIDE_START_PATH,
  indicatorPath,
  playbookPath,
  situationPath,
  startPath,
  termPath,
  themeTitle,
  useGuideIndex,
} from '@/entities/guide';

export function GuideHome() {
  const index = useGuideIndex();
  if (index.isError) {
    return <ErrorState title="The Guide failed to load." onRetry={() => void index.refetch()} />;
  }
  if (index.isPending) return <Skeleton variant="rect" height="lg" label="Loading the Guide" />;
  if (!index.data) return <EmptyState bordered title="The Guide has no entries." />;
  const { sections, themeGroups, families, situations, indicators, episodes, startPages, terms } =
    index.data;
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
              {section.id === 'start' && (
                <TextLink href={GUIDE_START_PATH} size="sm">
                  All the steps
                </TextLink>
              )}
              {section.id === 'glossary' && (
                <TextLink href={GUIDE_GLOSSARY_PATH} size="sm">
                  All the terms
                </TextLink>
              )}
              {section.id === 'regime' && (
                <TextLink href={GUIDE_REGIME_PATH} size="sm">
                  The warning signs and the falls
                </TextLink>
              )}
              {section.id === 'playbooks' && (
                <TextLink href={GUIDE_PLAYBOOKS_PATH} size="sm">
                  What each one says
                </TextLink>
              )}
              {section.id === 'situations' && (
                <TextLink href={GUIDE_SITUATIONS_PATH} size="sm">
                  Signs and what to do
                </TextLink>
              )}
              {section.id === 'fields' && (
                <Stack direction="row" gap={3}>
                  <TextLink href={fieldsPath({ view: 'intent' })} size="sm">
                    By intent
                  </TextLink>
                  <TextLink href={fieldsPath({ view: 'az' })} size="sm">
                    A to Z
                  </TextLink>
                </Stack>
              )}
            </Stack>
            <Text as="p" tone="secondary">
              {section.purpose}
            </Text>
            {section.id === 'start' && (
              <Stack as="ol" gap={2} aria-label="Start here pages, in reading order">
                {startPages.map((p) => (
                  <Stack as="li" key={p.id} direction="row" gap={3} align="baseline">
                    <Text tone="muted" mono>
                      {String(p.order)}
                    </Text>
                    <Stack gap={0}>
                      <TextLink href={startPath(p.id)}>{p.title}</TextLink>
                      <Text size="sm" tone="muted">
                        {p.summary}
                      </Text>
                    </Stack>
                  </Stack>
                ))}
              </Stack>
            )}
            {section.id === 'glossary' && (
              <Grid columns={2} gap={2} collapse="md" align="start">
                {terms.map((t) => (
                  <TextLink key={t.id} href={termPath(t.id)}>
                    {t.term}
                  </TextLink>
                ))}
              </Grid>
            )}
            {section.id === 'regime' && (
              <Grid columns={2} gap={5} collapse="md" align="start">
                <Stack gap={2} as="section" aria-label="Warning signs">
                  <Heading level={3} tone="muted">
                    Warning signs
                  </Heading>
                  {indicators.map((i) => (
                    <TextLink key={i.key} href={indicatorPath(i.key)}>
                      {i.plainName}
                    </TextLink>
                  ))}
                </Stack>
                <Stack gap={2} as="section" aria-label="Market falls">
                  <Heading level={3} tone="muted">
                    Market falls
                  </Heading>
                  {episodes.map((e) => (
                    <TextLink key={e.key} href={episodePath(e.key)}>
                      {e.name}
                    </TextLink>
                  ))}
                </Stack>
              </Grid>
            )}
            {section.id === 'playbooks' && (
              <Grid columns={2} gap={5} collapse="md" align="start">
                {families.map((family) => (
                  <Stack key={family.id} gap={2} as="section" aria-label={family.title}>
                    <Heading level={3} tone="muted">
                      {family.title}
                    </Heading>
                    {family.playbooks.map((p) => (
                      <TextLink key={p.id} href={playbookPath(p.id)}>
                        {p.name}
                      </TextLink>
                    ))}
                  </Stack>
                ))}
              </Grid>
            )}
            {section.id === 'fields' && (
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
            )}
            {section.id === 'situations' && (
              <Grid columns={2} gap={2} collapse="md" align="start">
                {situations.map((x) => (
                  <TextLink key={x.slug} href={situationPath(x.slug)}>
                    {`${x.name} · ${String(x.fields)}`}
                  </TextLink>
                ))}
              </Grid>
            )}
          </Stack>
        ))}
    </Stack>
  );
}
