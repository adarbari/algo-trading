/**
 * A site edge's Guide page (`/guide/edges/<id>`, ADR 0051, docs/ui/guide.md "Edges"), in a fixed
 * order: the idea (the thesis, with its status, asset, side and holding, and the way to the live
 * evidence), who is on the other side, why it lasts, what the research found (the published
 * figure and the planning haircut, where the document has one), how it is tested (each fact with
 * its glossary button), how it is built (its playbooks and the fields they read), what fools it,
 * whether you can trade it, the sources and related edges. Session-free: no win rate, verdict or
 * curve, only what the document says. The text is the server's; nothing is written here.
 */
import {
  Banner,
  Button,
  Chip,
  DocSection,
  EmptyState,
  ErrorState,
  Heading,
  KeyValue,
  NavList,
  ProseList,
  Skeleton,
  SourceList,
  Stack,
  StatStrip,
  StatusBadge,
  Text,
  TextLink,
} from '@algotrade/ui';
import { Fragment } from 'react';

import {
  EdgeRows,
  edgeSideText,
  edgeStatusText,
  edgeStatusTone,
  fieldPath,
  GUIDE_EDGES_PATH,
  GuideProse,
  mechanismPath,
  playbookPath,
  RelatedTerms,
  useGuideEdge,
} from '@/entities/guide';
import { termHelp } from '@/features/guide-help';

export interface GuideEdgeProps {
  /** The edge id in the URL. */
  id: string;
  /** Opens the live evidence: the Edges page with this edge chosen. */
  onSeeEvidence: () => void;
}

export function GuideEdge({ id, onSeeEvidence }: GuideEdgeProps) {
  const query = useGuideEdge(id);
  if (query.isError) {
    return <ErrorState title="The edge failed to load." onRetry={() => void query.refetch()} />;
  }
  if (query.isPending) return <Skeleton variant="rect" height="lg" label="Loading the edge" />;
  const edge = query.data;
  if (!edge) {
    return (
      <EmptyState
        bordered
        title="No such edge"
        description={`The Guide has no site edge called ${id}.`}
      />
    );
  }
  const { summary, research, mechanism } = edge;
  const linkedSources = edge.sources.filter((s) => s.url !== null);
  const fools = [edge.failureModes, edge.decoys].filter(
    (p): p is NonNullable<typeof p> => p != null,
  );
  return (
    <Stack gap={6}>
      <DocSection id="idea">
        <Stack gap={3} as="section" aria-label="Edge">
          <Stack direction="row" gap={2} wrap>
            <TextLink href={GUIDE_EDGES_PATH} size="sm">
              Edges
            </TextLink>
            {mechanism && (
              <TextLink href={mechanismPath(mechanism.id)} size="sm">
                {mechanism.title}
              </TextLink>
            )}
          </Stack>
          <Heading level={1} size="3xl">
            {summary.name}
          </Heading>
          <Text as="p" size="xl">
            <GuideProse prose={edge.thesis} size="xl" />
          </Text>
          <Stack direction="row" gap={2} align="center" wrap>
            <StatusBadge tone={edgeStatusTone(summary.status)}>
              {edgeStatusText(summary.status)}
            </StatusBadge>
            {termHelp('edge_status')}
            <Chip label={summary.assetText} />
            <Chip label={edgeSideText(summary.side)} />
            {termHelp(summary.sideTerm)}
            <Chip label={summary.holdingText} />
          </Stack>
          <Stack direction="row">
            <Button variant="primary" onClick={onSeeEvidence}>
              See the live evidence
            </Button>
          </Stack>
        </Stack>
      </DocSection>

      <DocSection id="other-side">
        <Stack gap={2}>
          <Heading level={2}>Who is on the other side</Heading>
          <Text as="p" tone="secondary">
            <GuideProse prose={edge.otherSide} tone="secondary" />
          </Text>
        </Stack>
      </DocSection>

      <DocSection id="lasts">
        <Stack gap={2}>
          <Heading level={2}>Why it lasts</Heading>
          <Text as="p" tone="secondary">
            <GuideProse prose={edge.lasts} tone="secondary" />
          </Text>
        </Stack>
      </DocSection>

      {research && (
        <DocSection id="research">
          <Stack gap={2}>
            <Stack direction="row" gap={2} align="center">
              <Heading level={2}>What the research found</Heading>
              {research.terms.map((term) => (
                <Fragment key={term}>{termHelp(term)}</Fragment>
              ))}
            </Stack>
            <StatStrip
              label="What the research found"
              items={[
                {
                  id: 'published',
                  label: research.measure,
                  value: research.figure,
                  sub: `${research.horizonText} · ${research.leg}`,
                },
                {
                  id: 'expect',
                  label: 'After our planning haircut',
                  value: research.expect,
                  sub: research.haircut,
                },
              ]}
            />
            <Text size="sm" tone="muted">
              {research.sample === null
                ? research.source
                : `${research.source} · ${research.sample}`}
            </Text>
          </Stack>
        </DocSection>
      )}

      <DocSection id="tested">
        <Stack gap={2}>
          <Heading level={2}>How we test it</Heading>
          <KeyValue
            label="How we test it"
            items={edge.tests.map((fact) => ({
              id: fact.key,
              label: fact.title,
              value: fact.text,
              ...(fact.term ? { action: termHelp(fact.term) } : {}),
            }))}
          />
        </Stack>
      </DocSection>

      {(edge.playbooks.length > 0 || edge.fields.length > 0) && (
        <DocSection id="built">
          <Stack gap={2}>
            <Heading level={2}>How it is built</Heading>
            {edge.playbooks.length > 0 && (
              <Stack gap={1}>
                <Text weight="semibold">Playbooks</Text>
                {edge.playbooks.map((p) => (
                  <TextLink key={p.id} href={playbookPath(p.id)}>
                    {p.family ? `${p.name} · ${p.family}` : p.name}
                  </TextLink>
                ))}
              </Stack>
            )}
            {edge.fields.length > 0 && (
              <Stack gap={1}>
                <Text weight="semibold">Fields it reads</Text>
                <Stack direction="row" gap={3} wrap>
                  {edge.fields.map((name) => (
                    <TextLink key={name} href={fieldPath(name)} mono size="sm">
                      {name}
                    </TextLink>
                  ))}
                </Stack>
              </Stack>
            )}
          </Stack>
        </DocSection>
      )}

      {(fools.length > 0 || edge.rejection) && (
        <DocSection id="fools">
          <Stack gap={2}>
            <Heading level={2}>What fools it</Heading>
            {edge.rejection && (
              <Banner tone={summary.status === 'rejected' ? 'negative' : 'warning'}>
                <Text as="p">
                  <GuideProse prose={edge.rejection} />
                </Text>
              </Banner>
            )}
            <ProseList
              aria-label="What fools it"
              items={fools.map((body, index) => ({
                id: String(index),
                body: <GuideProse prose={body} tone="secondary" />,
              }))}
            />
          </Stack>
        </DocSection>
      )}

      {edge.capacity && (
        <DocSection id="trade">
          <Stack gap={2}>
            <Heading level={2}>Can you trade it</Heading>
            <Text as="p" tone="secondary">
              <GuideProse prose={edge.capacity} tone="secondary" />
            </Text>
          </Stack>
        </DocSection>
      )}

      <DocSection id="sources">
        <Stack gap={2}>
          <Heading level={2}>Sources and further reading</Heading>
          <SourceList
            aria-label="Sources and further reading"
            items={linkedSources.map((source, index) => ({
              id: `s${String(index + 1)}`,
              kind: source.form,
              title: source.title,
              url: source.url ?? '',
            }))}
          />
          {edge.sources
            .filter((s) => s.url === null)
            .map((s) => (
              <Text key={s.title} size="sm" tone="muted">
                {`${s.form}: ${s.title}`}
              </Text>
            ))}
        </Stack>
      </DocSection>

      {(edge.related.length > 0 || edge.seeAlso.length > 0) && (
        <DocSection id="related">
          <Stack gap={2}>
            <Heading level={2}>Related</Heading>
            {edge.related.length > 0 && (
              <EdgeRows aria-label="Related edges" edges={edge.related} />
            )}
            <RelatedTerms ids={edge.seeAlso} />
          </Stack>
        </DocSection>
      )}
    </Stack>
  );
}

const SECTIONS = [
  { href: '#idea', label: 'The idea' },
  { href: '#other-side', label: 'Who is on the other side' },
  { href: '#lasts', label: 'Why it lasts' },
  { href: '#research', label: 'What the research found' },
  { href: '#tested', label: 'How we test it' },
  { href: '#built', label: 'How it is built' },
  { href: '#fools', label: 'What fools it' },
  { href: '#trade', label: 'Can you trade it' },
  { href: '#sources', label: 'Sources' },
] as const;

/** "On this page": the anchors of an edge page's sections, in the order they appear. */
export function EdgeOutline() {
  return <NavList aria-label="On this page" size="sm" items={SECTIONS} />;
}
