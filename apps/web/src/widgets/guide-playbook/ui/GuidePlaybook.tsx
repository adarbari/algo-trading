/**
 * A playbook's Guide page (ADR 0051, docs/ui/guide.md section 3): the header (preset id and
 * version, the summary as the hero, a way to today's hits and to the Builder), what a hit
 * looks like beside what it does not check, the criteria table, the caveats before acting, the
 * situations that fool its fields, related playbooks and the sources. The prose is the server's
 * (linked at catalogue names); a preset with no prose written shows its criteria alone.
 */
import {
  Banner,
  Button,
  DataTable,
  EmptyState,
  ErrorState,
  Grid,
  Heading,
  Mono,
  Skeleton,
  Stack,
  Surface,
  Text,
  TextLink,
} from '@algotrade/ui';

import { GuideProse, playbookPath, useGuidePlaybook, type GuideProseValue } from '@/entities/guide';

import { criteriaColumns } from '../model/columns';
import { BeforeActing } from './BeforeActing';

export interface GuidePlaybookProps {
  /** The preset id in the URL. */
  id: string;
  /** Opens that screener's results. */
  onSeeHits: () => void;
  /** Opens the preset in the Builder. */
  onOpenBuilder: () => void;
}

const COLUMNS = criteriaColumns();

function Block({ title, prose }: { title: string; prose: GuideProseValue }) {
  return (
    <Surface as="section" radius="lg" padding={3} aria-label={title}>
      <Stack gap={2}>
        <Heading level={2}>{title}</Heading>
        <Text as="p" tone="secondary">
          <GuideProse prose={prose} tone="secondary" />
        </Text>
      </Stack>
    </Surface>
  );
}

export function GuidePlaybook({ id, onSeeHits, onOpenBuilder }: GuidePlaybookProps) {
  const query = useGuidePlaybook(id);
  if (query.isError) {
    return <ErrorState title="The playbook failed to load." onRetry={() => void query.refetch()} />;
  }
  if (query.isPending) return <Skeleton variant="rect" height="lg" label="Loading the playbook" />;
  const playbook = query.data;
  if (!playbook) {
    return (
      <EmptyState
        bordered
        title="No such playbook"
        description={`There is no site screen called ${id}.`}
      />
    );
  }
  const { prose } = playbook;
  return (
    <Stack gap={6}>
      <Stack gap={3} as="section" aria-label="Playbook">
        <Mono size="sm" tone="muted">
          {`site preset · ${playbook.id}${playbook.version === null ? '' : ` v${String(playbook.version)}`}${playbook.familyTitle ? ` · ${playbook.familyTitle}` : ''}`}
        </Mono>
        <Heading level={1} size="3xl">
          {playbook.name}
        </Heading>
        {prose ? (
          <Text as="p" size="xl">
            <GuideProse prose={prose.summary} size="xl" />
          </Text>
        ) : (
          <Text as="p" tone="muted">
            No playbook prose is written for this screen yet; its criteria are below.
          </Text>
        )}
        <Stack direction="row" gap={2} wrap>
          <Button variant="primary" onClick={onSeeHits}>
            See today’s hits
          </Button>
          <Button onClick={onOpenBuilder}>Open in Builder</Button>
        </Stack>
      </Stack>

      {prose && (
        <Grid columns={2} gap={3} collapse="md" align="start">
          <Block title="What a hit looks like" prose={prose.hit} />
          <Banner tone="warning" title="What it does not check">
            <Text as="p">
              <GuideProse prose={prose.notChecked} />
            </Text>
          </Banner>
        </Grid>
      )}

      <Stack gap={2} as="section" aria-label="The criteria">
        <Heading level={2}>The criteria</Heading>
        <DataTable
          label={`${playbook.name} criteria`}
          columns={COLUMNS}
          rows={playbook.criteria}
          getRowId={(row) => row.name}
          visibleRows={Math.max(playbook.criteria.length, 1)}
          activateOnClick={false}
          emptyMessage="This screen has no criteria."
        />
        {playbook.tieBreak && (
          <Text size="sm" tone="muted">
            {`Ranked by ${playbook.tieBreak}, ${playbook.tieBreakDescending ? 'highest' : 'lowest'} first.`}
          </Text>
        )}
      </Stack>

      {prose && <BeforeActing caveats={prose.beforeActing} situations={playbook.situations} />}

      {playbook.related.length > 0 && (
        <Stack gap={2} as="section" aria-label="Related playbooks">
          <Heading level={2}>Related playbooks</Heading>
          <Stack gap={1}>
            {playbook.related.map((r) => (
              <Text key={r.id} size="sm">
                <TextLink href={playbookPath(r.id)} size="inherit">
                  {r.name}
                </TextLink>
                {`: ${r.reason}`}
              </Text>
            ))}
          </Stack>
        </Stack>
      )}

      {prose && prose.sources.length > 0 && (
        <Stack gap={2} as="section" aria-label="Sources">
          <Heading level={2}>Sources</Heading>
          <Stack gap={1}>
            {prose.sources.map((source) => (
              <Text key={source} size="sm" tone="muted">
                {source}
              </Text>
            ))}
          </Stack>
        </Stack>
      )}
    </Stack>
  );
}
