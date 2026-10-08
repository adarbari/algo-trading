/**
 * The public kinds of a gap (ADR 0056) in words: a title per kind and one line for a tooltip.
 * The Guide term the server names explains each at length; render by `kind`, never by the
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

export const KIND_TEXT: Record<UnavailableKindName, string> = {
  SYSTEM: 'not available because of a system error',
  NOT_STORED: 'not available for this instrument',
  NOT_APPLICABLE: 'does not apply to this instrument',
  ILLIQUID: 'not available: too thinly traded today',
  LICENCE: 'not available under your data licence',
  NOT_RUN: 'not run for this session',
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
