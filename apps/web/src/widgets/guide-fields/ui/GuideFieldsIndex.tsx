/**
 * The field index (`/guide/fields`): every guided field by theme (the themes grouped in the
 * order a screen uses them, with the server's counts), by intent (what a trader wants to do,
 * with the fields that offer a criterion for it) or A to Z. Narrowing to one theme or intent
 * lists its fields, each a link to its page with the first sentence of how to read it.
 */
import {
  EmptyState,
  ErrorState,
  Grid,
  Heading,
  SegmentedControl,
  Skeleton,
  Stack,
  Text,
  TextLink,
} from '@algotrade/ui';
import { useMemo } from 'react';

import {
  shortMeaning,
  themeFields,
  useFeatureCatalogue,
  type CatalogueFeature,
} from '@/entities/feature';
import {
  fieldPath,
  fieldsPath,
  themeTitle,
  useGuideIndex,
  type FieldsView,
} from '@/entities/guide';

const VIEWS = [
  { value: 'theme', label: 'By theme' },
  { value: 'intent', label: 'By intent' },
  { value: 'az', label: 'A to Z' },
] as const;

export interface GuideFieldsIndexProps {
  view?: FieldsView | undefined;
  theme?: string | undefined;
  intent?: string | undefined;
  onViewChange: (view: FieldsView) => void;
}

/** Fields as links, each with the first sentence of how to read it. */
function FieldList({
  fields,
  emptyMessage,
}: {
  fields: readonly CatalogueFeature[];
  emptyMessage: string;
}) {
  if (fields.length === 0) return <EmptyState bordered compact title={emptyMessage} />;
  return (
    <Stack gap={2}>
      {fields.map((f) => (
        <Stack key={f.name} gap={0}>
          <TextLink href={fieldPath(f.name)} mono size="sm">
            {f.name}
          </TextLink>
          <Text size="sm" tone="muted">
            {shortMeaning(f)}
          </Text>
        </Stack>
      ))}
    </Stack>
  );
}

export function GuideFieldsIndex({
  view = 'theme',
  theme,
  intent,
  onViewChange,
}: GuideFieldsIndexProps) {
  const index = useGuideIndex();
  const catalogue = useFeatureCatalogue();
  const guided = useMemo(
    () => (catalogue.data ?? []).filter((f) => Boolean(f.guide)),
    [catalogue.data],
  );
  const section = index.data?.sections.find((s) => s.id === 'fields');

  if (index.isError || catalogue.isError) {
    return (
      <ErrorState
        title="The field index failed to load."
        onRetry={() => {
          void index.refetch();
          void catalogue.refetch();
        }}
      />
    );
  }
  if (index.isPending || catalogue.isPending)
    return <Skeleton variant="rect" height="lg" label="Loading the field index" />;
  const data = index.data;
  if (!data) return <EmptyState bordered title="The Guide has no field index." />;

  let body;
  if (view === 'intent') {
    const offered = intent
      ? guided.filter((f) => f.guide?.uses.some((u) => u.intent === intent))
      : null;
    body = offered ? (
      <Stack gap={3}>
        <Heading level={2}>{intent}</Heading>
        <TextLink href={fieldsPath({ view: 'intent' })} size="sm">
          All intents
        </TextLink>
        <FieldList fields={offered} emptyMessage="No field offers a criterion for this intent." />
      </Stack>
    ) : (
      <Grid columns={2} gap={2} collapse="md">
        {data.intents.map((i) => (
          <TextLink key={i.intent} href={fieldsPath({ view: 'intent', intent: i.intent })}>
            {`${i.intent} · ${String(i.fields)}`}
          </TextLink>
        ))}
      </Grid>
    );
  } else if (view === 'az') {
    body = (
      <FieldList
        fields={[...guided].sort((a, b) => a.name.localeCompare(b.name))}
        emptyMessage="The guide has no fields."
      />
    );
  } else if (theme) {
    body = (
      <Stack gap={3}>
        <Heading level={2}>{themeTitle(theme)}</Heading>
        <TextLink href={fieldsPath()} size="sm">
          All themes
        </TextLink>
        <FieldList
          fields={themeFields(guided, theme)}
          emptyMessage="No guided field in this theme."
        />
      </Stack>
    );
  } else {
    body = (
      <Grid columns={2} gap={5} collapse="md" align="start">
        {data.themeGroups.map((group) => (
          <Stack key={group.id} gap={2} as="section" aria-label={group.title}>
            <Heading level={2}>{group.title}</Heading>
            {group.themes.map((t) => (
              <TextLink key={t.theme} href={fieldsPath({ theme: t.theme })}>
                {`${themeTitle(t.theme)} · ${String(t.fields)}`}
              </TextLink>
            ))}
          </Stack>
        ))}
      </Grid>
    );
  }

  return (
    <Stack gap={4}>
      <Stack gap={1}>
        <Heading level={1}>Fields</Heading>
        {section && (
          <Text as="p" tone="secondary">
            {section.purpose}
          </Text>
        )}
      </Stack>
      <Stack direction="row">
        <SegmentedControl
          aria-label="Browse fields"
          options={VIEWS}
          value={view}
          onValueChange={onViewChange}
        />
      </Stack>
      {body}
    </Stack>
  );
}
