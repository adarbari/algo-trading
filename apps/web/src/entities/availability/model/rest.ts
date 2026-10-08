/**
 * The REST previews (the Builder's screen preview, a formula check) send `unavailable` in the
 * API's snake_case with the chain as a bare list; this reads them as the GraphQL shape the
 * notes draw (ADR 0056). Nothing is decided here: the server already withheld what a trader
 * may not see.
 */
import type { CauseLevelName, ServedUnavailable, UnavailableKindName } from './served';

interface RestLink {
  level: string;
  subject: string;
  status: string;
  message: string;
  run_id?: string | null | undefined;
}

export interface RestUnavailable {
  kind: string;
  features: string[];
  guide_term: string;
  kind_text: string;
  cause?: RestLink[] | null | undefined;
}

export function fromRest(gaps: readonly RestUnavailable[] | undefined): ServedUnavailable[] {
  return (gaps ?? []).map((gap) => ({
    kind: gap.kind as UnavailableKindName,
    features: gap.features,
    guideTerm: gap.guide_term,
    kindText: gap.kind_text,
    cause: gap.cause
      ? {
          links: gap.cause.map((link) => ({
            level: link.level as CauseLevelName,
            subject: link.subject,
            status: link.status,
            message: link.message,
            runId: link.run_id ?? null,
          })),
        }
      : null,
  }));
}
