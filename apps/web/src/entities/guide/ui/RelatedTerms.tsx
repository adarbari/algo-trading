/**
 * The glossary terms an entry sends the reader on to (`seeAlso`, ids): each a link to the term's
 * page named by the term itself (read in the page's Guide batch), so the page never writes a
 * name. A term the Guide lacks is left out.
 */
import { Stack, TextLink } from '@algotrade/ui';

import { useGuideTerm } from '../api/hooks';
import { termPath } from '../model/paths';

function RelatedTerm({ id }: { id: string }) {
  const term = useGuideTerm(id).data;
  if (!term) return null;
  return <TextLink href={termPath(id)}>{term.entry.term}</TextLink>;
}

export interface RelatedTermsProps {
  /** Glossary term ids. */
  ids: readonly string[];
}

export function RelatedTerms({ ids }: RelatedTermsProps) {
  return (
    <Stack direction="row" gap={3} wrap>
      {ids.map((id) => (
        <RelatedTerm key={id} id={id} />
      ))}
    </Stack>
  );
}
