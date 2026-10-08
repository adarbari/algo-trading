/**
 * One regime indicator's Guide page: the question it answers (plain name over the technical one)
 * with the one-liner as the hero, why it matters, when it is on, lead time and track record,
 * what it did before each reference fall (each linked to the fall's page), how it is computed,
 * the market feature it reads (a link to its card on the Regime page, there being no market field
 * pages) and its reading list. The text is the server's, from `config/site/regime/cards.toml`.
 */
import {
  EmptyState,
  ErrorState,
  ExternalLink,
  Heading,
  LinkedText,
  Mono,
  Skeleton,
  Stack,
  Text,
  TextLink,
} from '@algotrade/ui';

import {
  episodePath,
  GuideProse,
  REGIME_PAGE_PATH,
  useGuideIndicator,
  type GuideProseValue,
} from '@/entities/guide';

export interface GuideIndicatorProps {
  /** The indicator's key in the URL. */
  indicatorKey: string;
}

function Section({ title, prose }: { title: string; prose: GuideProseValue[] }) {
  return (
    <Stack gap={2} as="section" aria-label={title}>
      <Heading level={2}>{title}</Heading>
      {prose.map((p) => (
        <Text as="p" key={p.segments.map((s) => s.text).join('')}>
          <GuideProse prose={p} />
        </Text>
      ))}
    </Stack>
  );
}

export function GuideIndicator({ indicatorKey }: GuideIndicatorProps) {
  const query = useGuideIndicator(indicatorKey);
  if (query.isError) {
    return (
      <ErrorState title="The indicator failed to load." onRetry={() => void query.refetch()} />
    );
  }
  if (query.isPending) return <Skeleton variant="rect" height="lg" label="Loading the indicator" />;
  const indicator = query.data;
  if (!indicator) {
    return (
      <EmptyState
        bordered
        title="No such indicator"
        description={`The Guide has no warning sign called ${indicatorKey}.`}
      />
    );
  }
  return (
    <Stack gap={6}>
      <Stack gap={2} as="section" aria-label="Indicator">
        <Text size="sm" tone="muted">
          {`${indicator.pace === 'slow' ? 'Slow-moving' : 'Fast-moving'} warning sign · ${indicator.technicalName}`}
        </Text>
        <Heading level={1} size="3xl">
          {indicator.plainName}
        </Heading>
        <Text as="p" size="xl">
          <GuideProse prose={indicator.summary} size="xl" />
        </Text>
        <TextLink href={REGIME_PAGE_PATH} size="sm">
          Today’s reading on the Regime page
        </TextLink>
      </Stack>
      <Section title="Why it matters" prose={[indicator.whyItMatters]} />
      <Section title="When it is on" prose={[indicator.whatOnMeans]} />
      <Section
        title="Lead time and track record"
        prose={[indicator.leadTime, indicator.trackRecord]}
      />
      {indicator.before.length > 0 && (
        <Stack gap={2} as="section" aria-label="What it did before">
          <Heading level={2}>What it did before</Heading>
          <Stack as="ul" gap={2}>
            {indicator.before.map((entry) => (
              <Stack as="li" key={entry.label} gap={0}>
                {entry.episode ? (
                  <TextLink href={episodePath(entry.episode)}>{entry.label}</TextLink>
                ) : (
                  <Text weight="medium">{entry.label}</Text>
                )}
                <Text size="sm" tone="secondary">
                  <GuideProse prose={entry.line} tone="secondary" size="sm" />
                </Text>
              </Stack>
            ))}
          </Stack>
        </Stack>
      )}
      <Stack gap={2} as="section" aria-label="How it is computed">
        <Heading level={2}>How it is computed</Heading>
        <LinkedText
          parts={indicator.how.map((part) => ({
            text: part.text,
            ...(part.url === null ? {} : { href: part.url }),
          }))}
        />
        <Text size="sm" tone="muted">
          Reads <Mono size="sm">{indicator.feature}</Mono>; its card on the Regime page shows
          today’s value.
        </Text>
      </Stack>
      {indicator.sources.length > 0 && (
        <Stack gap={2} as="section" aria-label="Sources">
          <Heading level={2}>Sources</Heading>
          <Stack as="ul" gap={1}>
            {indicator.sources.map((link) => (
              <Stack as="li" key={link.url}>
                <ExternalLink size="sm" href={link.url}>
                  {link.title}
                </ExternalLink>
              </Stack>
            ))}
          </Stack>
        </Stack>
      )}
    </Stack>
  );
}
