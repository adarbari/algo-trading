/**
 * A mechanism's Guide page (`/guide/edges/m/<id>`, ADR 0051, docs/ui/guide.md "Edges"): the
 * question it answers, its title and one-line hero, how it works, why it survives, the research
 * behind the family (stat tiles with their citation, then the paragraphs), how to tell a real
 * edge from a decoy and the one thing not to read into it, the edges that rest on it, the ideas
 * researched but not built, the sources and the glossary terms it sends the reader to. The text
 * is the mechanism file's, as the server links it; nothing is written here.
 */
import {
  Banner,
  DocSection,
  EmptyState,
  ErrorState,
  Heading,
  NavList,
  ProseList,
  Skeleton,
  SourceList,
  Stack,
  StatStrip,
  Text,
  TextLink,
} from '@algotrade/ui';

import {
  EdgeRows,
  EDGES_PAGE_PATH,
  GUIDE_EDGES_PATH,
  GuideProse,
  IdeaRows,
  RelatedTerms,
  useGuideMechanism,
  type GuideProseValue,
} from '@/entities/guide';
import { termHelp } from '@/features/guide-help';

export interface GuideMechanismProps {
  /** The mechanism id in the URL. */
  id: string;
}

const paragraphs = (prefix: string, prose: readonly GuideProseValue[]) =>
  prose.map((body, index) => ({
    id: `${prefix}${String(index)}`,
    body: <GuideProse prose={body} tone="secondary" />,
  }));

export function GuideMechanism({ id }: GuideMechanismProps) {
  const query = useGuideMechanism(id);
  if (query.isError) {
    return (
      <ErrorState title="The mechanism failed to load." onRetry={() => void query.refetch()} />
    );
  }
  if (query.isPending) return <Skeleton variant="rect" height="lg" label="Loading the mechanism" />;
  const m = query.data;
  if (!m) {
    return (
      <EmptyState
        bordered
        title="No such mechanism"
        description={`The Guide has no mechanism called ${id}.`}
      />
    );
  }
  return (
    <Stack gap={6}>
      <Stack gap={2} as="section" aria-label="Mechanism">
        <Stack direction="row">
          <TextLink href={GUIDE_EDGES_PATH} size="sm">
            Edges
          </TextLink>
        </Stack>
        <Text tone="muted">{m.question}</Text>
        <Heading level={1} size="3xl">
          {m.title}
        </Heading>
        <Text as="p" size="xl">
          {m.short}
        </Text>
      </Stack>

      <DocSection id="how">
        <Stack gap={2}>
          <Heading level={2}>How it works</Heading>
          {m.howItWorks.map((body, index) => (
            <Text as="p" tone="secondary" key={String(index)}>
              <GuideProse prose={body} tone="secondary" />
            </Text>
          ))}
        </Stack>
      </DocSection>

      <DocSection id="survives">
        <Stack gap={2}>
          <Heading level={2}>Why it survives</Heading>
          <ProseList aria-label="Why it survives" items={paragraphs('survives', m.whyItSurvives)} />
        </Stack>
      </DocSection>

      <DocSection id="research">
        <Stack gap={2}>
          <Heading level={2}>What the research says</Heading>
          <StatStrip
            label="Research figures"
            items={m.stats.map((stat) => ({
              id: stat.title,
              label: stat.title,
              value: stat.value,
              sub: (
                <>
                  {stat.reading}
                  {stat.source !== null && (
                    <>
                      {' '}
                      <TextLink href={`#s${String(stat.source)}`} size="inherit">
                        {`[${String(stat.source)}]`}
                      </TextLink>
                    </>
                  )}
                </>
              ),
            }))}
          />
          {m.research.map((body, index) => (
            <Text as="p" tone="secondary" key={String(index)}>
              <GuideProse prose={body} tone="secondary" />
            </Text>
          ))}
        </Stack>
      </DocSection>

      <DocSection id="decoy">
        <Stack gap={2}>
          <Heading level={2}>Real one or decoy</Heading>
          <ProseList aria-label="Real one or decoy" items={paragraphs('decoy', m.realVsDecoy)} />
          <Banner tone="warning">
            <Text as="p">
              <GuideProse prose={m.dont} />
            </Text>
          </Banner>
        </Stack>
      </DocSection>

      <DocSection id="edges">
        <Stack gap={3} as="section" aria-label="The edges in this mechanism">
          <Stack direction="row" gap={2} align="center" wrap>
            <Heading level={2}>The edges in this mechanism</Heading>
            {termHelp('edge_status')}
            <TextLink href={EDGES_PAGE_PATH} size="sm">
              Live results on the Edges page
            </TextLink>
          </Stack>
          {m.edges.length === 0 ? (
            <EmptyState bordered title="No edge rests on this mechanism yet." />
          ) : (
            <EdgeRows aria-label="Edges" edges={m.edges} />
          )}
        </Stack>
      </DocSection>

      {m.notBuilt.length > 0 && (
        <DocSection id="not-built">
          <Stack gap={3} as="section" aria-label="Researched, not built">
            <Stack direction="row" gap={2} align="center">
              <Heading level={2}>Researched, not built</Heading>
              {termHelp('idea_verdict')}
              {termHelp('idea_feasibility')}
            </Stack>
            <IdeaRows aria-label="Ideas not built" ideas={m.notBuilt} />
          </Stack>
        </DocSection>
      )}

      <DocSection id="sources">
        <Stack gap={2}>
          <Heading level={2}>Sources and further reading</Heading>
          <SourceList
            aria-label="Sources and further reading"
            items={m.sources.map((source, index) => ({
              id: `s${String(index + 1)}`,
              title: source.title,
              url: source.url,
              why: source.reading,
            }))}
          />
        </Stack>
      </DocSection>

      {m.seeAlso.length > 0 && (
        <DocSection id="related">
          <Stack gap={2}>
            <Heading level={2}>Related</Heading>
            <RelatedTerms ids={m.seeAlso} />
          </Stack>
        </DocSection>
      )}
    </Stack>
  );
}

const SECTIONS = [
  { href: '#how', label: 'How it works' },
  { href: '#survives', label: 'Why it survives' },
  { href: '#research', label: 'What the research says' },
  { href: '#decoy', label: 'Real one or decoy' },
  { href: '#edges', label: 'The edges' },
  { href: '#not-built', label: 'Researched, not built' },
  { href: '#sources', label: 'Sources' },
] as const;

/** "On this page": the anchors of a mechanism page's sections, in the order they appear. */
export function MechanismOutline() {
  return <NavList aria-label="On this page" size="sm" items={SECTIONS} />;
}
