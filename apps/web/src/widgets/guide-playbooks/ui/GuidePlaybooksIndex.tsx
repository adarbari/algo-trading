/**
 * The playbook index (`/guide/playbooks`): the families in the Guide's order (`sections.toml`),
 * each playbook a link to its page with its summary. The summaries are the playbook reads the
 * playbook pages share, so opening one afterwards is instant.
 */
import { EmptyState, ErrorState, Heading, Skeleton, Stack, Text, TextLink } from '@algotrade/ui';

import { GuideProse, playbookPath, useGuideIndex, useGuidePlaybook } from '@/entities/guide';

function PlaybookEntry({ id, name }: { id: string; name: string }) {
  const playbook = useGuidePlaybook(id);
  const summary = playbook.data?.prose?.summary;
  return (
    <Stack gap={1}>
      <TextLink href={playbookPath(id)}>{name}</TextLink>
      {summary && (
        <Text as="p" size="sm" tone="secondary">
          <GuideProse prose={summary} size="sm" tone="secondary" />
        </Text>
      )}
    </Stack>
  );
}

export function GuidePlaybooksIndex() {
  const index = useGuideIndex();
  if (index.isError) {
    return <ErrorState title="The Guide failed to load." onRetry={() => void index.refetch()} />;
  }
  if (index.isPending) return <Skeleton variant="rect" height="lg" label="Loading the playbooks" />;
  const section = index.data?.sections.find((s) => s.id === 'playbooks');
  const families = index.data?.families ?? [];
  if (families.length === 0) return <EmptyState bordered title="The Guide has no playbooks." />;
  return (
    <Stack gap={6}>
      <Stack gap={1}>
        <Heading level={1} size="3xl">
          {section?.title ?? 'Playbooks'}
        </Heading>
        {section && (
          <Text as="p" tone="secondary">
            {section.purpose}
          </Text>
        )}
      </Stack>
      {families.map((family) => (
        <Stack key={family.id} gap={3} as="section" aria-label={family.title}>
          <Heading level={2}>{family.title}</Heading>
          {family.playbooks.map((p) => (
            <PlaybookEntry key={p.id} id={p.id} name={p.name} />
          ))}
        </Stack>
      ))}
    </Stack>
  );
}
