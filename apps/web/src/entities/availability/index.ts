/**
 * Entity: why something is not available (ADR 0056). The shapes the server sends for a gap
 * (`Unknown`, `Unavailable`: a public kind, its Guide term, and for an admin the cause chain),
 * the notes that draw them (`UnavailableNote` per kind, `UnknownNote` for one value) and the
 * words for a value's gap. The only place a gap's `cause` and `code` are read (ESLint rule 11);
 * the server decides who may see a cause, never the browser.
 */
export { groupByKind, type KindGroup } from './model/group';
export { TermHelpProvider, type RenderTermHelp } from './model/help';
export { KIND_TITLE } from './model/kinds';
export type {
  CauseLevelName,
  ServedCause,
  ServedCauseLink,
  ServedUnavailable,
  ServedUnknown,
  UnavailableKindName,
} from './model/served';
export { fromRest, type RestUnavailable } from './model/rest';
export { unknownText, unknownWord } from './model/unknown';
export {
  cellText,
  cellWord,
  reasonLabel,
  reasonText,
  type NullReasonName,
  type UnknownCodeName,
} from './model/words';
export { UnavailableNote, type UnavailableNoteProps } from './ui/UnavailableNote';
export { UnknownNote, type UnknownNoteProps } from './ui/UnknownNote';
