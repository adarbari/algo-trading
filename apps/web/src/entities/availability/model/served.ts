/**
 * What the server sends about a gap (ADR 0056): an `Unknown` (one value) or an `Unavailable`
 * (the features a table-level gap leaves out), each with a public `kind`, its Guide term and,
 * for an admin only, the `cause` chain. The server withholds the chain from anyone else; the
 * browser never checks a role. These are the shapes every operation selects.
 */
import type { gqlTypes } from '@/shared/api';

import type { NullReasonName, UnknownCodeName } from './words';

export type UnavailableKindName = gqlTypes.UnavailableKind;
export type CauseLevelName = gqlTypes.CauseLevel;

export interface ServedCauseLink {
  level: CauseLevelName;
  subject: string;
  status: string;
  message: string;
  runId?: string | null | undefined;
}

export interface ServedCause {
  links: readonly ServedCauseLink[];
}

/** A value not known for the session, as an operation selects it. */
export interface ServedUnknown {
  code: UnknownCodeName;
  reason?: NullReasonName | null | undefined;
  kind: UnavailableKindName;
  guideTerm: string;
  /** The kind in the server's generic words (never a table, vendor or step). */
  kindText: string;
  cause?: ServedCause | null | undefined;
}

/** The features a gap leaves out, with the one kind that says why. */
export interface ServedUnavailable {
  kind: UnavailableKindName;
  features: readonly string[];
  guideTerm: string;
  kindText: string;
  cause?: ServedCause | null | undefined;
}
