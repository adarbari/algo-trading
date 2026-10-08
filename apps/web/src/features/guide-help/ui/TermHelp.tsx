/**
 * A glossary term's help: the term, its one-sentence definition and the paragraph behind it.
 * The text is the term's (`config/site/guide/glossary.toml`) as the server links it; nothing is
 * written here, so any word of the app can carry an InfoButton by naming the term's id.
 */
import { HelpLead, HelpSection, Text } from '@algotrade/ui';

import { GuideProse, useGuideTerm } from '@/entities/guide';

import { HelpShell } from './HelpShell';

export function TermHelp({ id }: { id: string }) {
  const query = useGuideTerm(id);
  const term = query.data;
  return (
    <HelpShell
      entry={{ kind: 'term', id }}
      label={`What is ${term?.entry.term ?? 'this term'}?`}
      title={term?.entry.term ?? 'Glossary term'}
      eyebrow="Glossary"
      summary={term?.entry.short}
      state={query.isPending ? 'pending' : query.isError ? 'error' : !term ? 'missing' : 'ready'}
      missingText="The Guide has no entry for this term yet."
      onRetry={() => {
        void query.refetch();
      }}
      retrying={query.isFetching}
    >
      {term && (
        <>
          <HelpLead>{term.entry.short}</HelpLead>
          <HelpSection title="In detail">
            <Text as="p">
              <GuideProse prose={term.body} />
            </Text>
          </HelpSection>
        </>
      )}
    </HelpShell>
  );
}
