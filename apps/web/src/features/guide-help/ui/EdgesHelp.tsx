/**
 * The help of an Edges entry: a mechanism (its question, its one-line hero, how it works and why
 * it survives) or a site edge (its thesis, status, who is on the other side and why it lasts).
 * "Open full page" has the rest. The text is the mechanism file's or the edge document's as the
 * server links it (`config/site/guide/mechanisms/`, `config/site/edges/`); nothing is written
 * here.
 */
import { HelpLead, HelpSection, Text } from '@algotrade/ui';

import { edgeStatusText, GuideProse, useGuideEdge, useGuideMechanism } from '@/entities/guide';

import { HelpShell } from './HelpShell';

function MechanismHelp({ id }: { id: string }) {
  const query = useGuideMechanism(id);
  const m = query.data;
  const how = m?.howItWorks[0];
  const survives = m?.whyItSurvives[0];
  return (
    <HelpShell
      entry={{ kind: 'mechanism', id }}
      label={`About ${m?.title ?? 'this mechanism'}`}
      title={m?.title ?? 'Mechanism'}
      eyebrow="Mechanism"
      {...(m ? { meta: m.question } : {})}
      summary={m?.short}
      state={query.isPending ? 'pending' : query.isError ? 'error' : !m ? 'missing' : 'ready'}
      missingText="The Guide has no entry for this mechanism yet."
      onRetry={() => {
        void query.refetch();
      }}
      retrying={query.isFetching}
    >
      {m && (
        <>
          <HelpLead>{m.short}</HelpLead>
          {how && (
            <HelpSection title="How it works">
              <Text as="p">
                <GuideProse prose={how} />
              </Text>
            </HelpSection>
          )}
          {survives && (
            <HelpSection title="Why it survives">
              <Text as="p">
                <GuideProse prose={survives} />
              </Text>
            </HelpSection>
          )}
        </>
      )}
    </HelpShell>
  );
}

function EdgeHelp({ id }: { id: string }) {
  const query = useGuideEdge(id);
  const edge = query.data;
  return (
    <HelpShell
      entry={{ kind: 'edge', id }}
      label={`About ${edge?.summary.name ?? 'this edge'}`}
      title={edge?.summary.name ?? 'Edge'}
      eyebrow="Edge"
      {...(edge ? { meta: edgeStatusText(edge.summary.status) } : {})}
      summary={edge?.summary.thesis}
      state={query.isPending ? 'pending' : query.isError ? 'error' : !edge ? 'missing' : 'ready'}
      missingText="The Guide has no entry for this edge yet."
      onRetry={() => {
        void query.refetch();
      }}
      retrying={query.isFetching}
    >
      {edge && (
        <>
          <HelpLead>
            <GuideProse prose={edge.thesis} />
          </HelpLead>
          <HelpSection title="Who is on the other side">
            <Text as="p">
              <GuideProse prose={edge.otherSide} />
            </Text>
          </HelpSection>
          <HelpSection title="Why it lasts">
            <Text as="p">
              <GuideProse prose={edge.lasts} />
            </Text>
          </HelpSection>
        </>
      )}
    </HelpShell>
  );
}

/** The drawer of a mechanism or a site edge (one lazy module for both). */
export default function EdgesHelp({
  entry,
}: {
  entry: { kind: 'mechanism' | 'edge'; id: string };
}) {
  return entry.kind === 'mechanism' ? <MechanismHelp id={entry.id} /> : <EdgeHelp id={entry.id} />;
}
