/**
 * What the builder edits (`Query.edge(id)`): the settings of the edge as its layered document
 * resolves, the user's own document (a save sends the whole document) and the few document
 * fields the edges list does not carry. Written by hand, not through `graphql()`, so the
 * operation stays out of the entry chunk's generated map; keyed under `EdgesPage` so a save or a
 * run reads it again.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, queryKeys, TypedDocumentString } from '@/shared/api';

export interface EdgeSettings {
  schedule: string;
  frozenFrom: string | null;
  replaces: string | null;
  settings: {
    topK: number | null;
    universe: string;
    kind: string;
    benchmark: string;
    startOffsetSessions: number;
    costBps: number | null;
    qualityBar: { key: string; text: string }[];
    /** The user's own document as JSON (`{}` for a site edge). */
    own: Record<string, unknown>;
  } | null;
}

const Document = new TypedDocumentString<{ edge: EdgeSettings | null }, { id: string }>(
  `query EdgeBuilder($id: String!) { edge(id: $id) { schedule frozenFrom replaces settings {
    topK universe kind benchmark startOffsetSessions costBps qualityBar { key text } own } } }`,
);

export function useEdgeSettings(id: string | null) {
  return useQuery({
    queryKey: queryKeys.gql('EdgesPage', { builder: id }),
    queryFn: () => gql(Document, { id: id ?? '' }),
    select: (data) => data.edge,
    enabled: id !== null,
  });
}
