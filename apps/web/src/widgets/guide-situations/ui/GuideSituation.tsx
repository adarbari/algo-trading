/**
 * One situation's Guide page: how it shows itself (signs), what a screen does about it (the
 * field names linked to their pages), every field it fools and the playbooks reading any of them.
 */
import {
  EmptyState,
  ErrorState,
  Heading,
  Skeleton,
  Stack,
  Surface,
  Text,
  TextLink,
} from '@algotrade/ui';

import { fieldPath, GuideProse, playbookPath, useGuideSituation } from '@/entities/guide';

export interface GuideSituationProps {
  /** The situation's slug in the URL. */
  slug: string;
}

export function GuideSituation({ slug }: GuideSituationProps) {
  const query = useGuideSituation(slug);
  if (query.isError) {
    return (
      <ErrorState title="The situation failed to load." onRetry={() => void query.refetch()} />
    );
  }
  if (query.isPending) return <Skeleton variant="rect" height="lg" label="Loading the situation" />;
  const situation = query.data;
  if (!situation) {
    return (
      <EmptyState
        bordered
        title="No such situation"
        description={`The Guide has no situation called ${slug}.`}
      />
    );
  }
  return (
    <Stack gap={6}>
      <Stack gap={1}>
        <Text size="sm" tone="muted">
          Situation
        </Text>
        <Heading level={1} size="3xl">
          {situation.name}
        </Heading>
      </Stack>
      <Stack gap={2} as="section" aria-label="Signs">
        <Heading level={2}>Signs</Heading>
        <Text as="p" size="lg">
          <GuideProse prose={situation.signs} size="lg" />
        </Text>
      </Stack>
      <Surface as="section" radius="lg" padding={3} aria-label="What to do">
        <Stack gap={2}>
          <Heading level={2}>What to do</Heading>
          <Text as="p">
            <GuideProse prose={situation.do} />
          </Text>
        </Stack>
      </Surface>
      <Stack gap={2} as="section" aria-label="Fields it fools">
        <Heading level={2}>Fields it fools</Heading>
        <Stack gap={1}>
          {situation.affects.map((name) => (
            <TextLink key={name} href={fieldPath(name)} mono size="sm">
              {name}
            </TextLink>
          ))}
        </Stack>
      </Stack>
      <Stack gap={2} as="section" aria-label="Playbooks it affects">
        <Heading level={2}>Playbooks it affects</Heading>
        {situation.playbooks.length === 0 ? (
          <Text size="sm" tone="muted">
            No site screen reads a field it fools.
          </Text>
        ) : (
          situation.playbooks.map((p) => (
            <Stack key={p.id} gap={0}>
              <TextLink href={playbookPath(p.id)}>{p.name}</TextLink>
              <Text size="sm" tone="muted">
                {`reads ${p.fields.join(', ')}`}
              </Text>
            </Stack>
          ))
        )}
      </Stack>
    </Stack>
  );
}
