/**
 * The public kinds of a gap (ADR 0056): a title per kind. The generic words of a kind come from
 * the server (`kindText`); the Guide term the server names explains each at length; render by `kind`, never by the
 * `code` (a NO_ROW can be a SYSTEM gap).
 */
import type { UnavailableKindName } from './served';

export const KIND_TITLE: Record<UnavailableKindName, string> = {
  SYSTEM: 'Not available: system error',
  NOT_STORED: 'Not available for this instrument',
  NOT_APPLICABLE: 'Does not apply',
  ILLIQUID: 'Too thinly traded',
  LICENCE: 'Licence',
  NOT_RUN: 'Not run',
};

/** The order kinds are listed in: a real failure first. */
export const KIND_ORDER: readonly UnavailableKindName[] = [
  'SYSTEM',
  'NOT_STORED',
  'NOT_RUN',
  'LICENCE',
  'ILLIQUID',
  'NOT_APPLICABLE',
];
