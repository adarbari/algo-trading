/**
 * Why a draft did not arrive, as the trader reads it. The API's refusals carry the server's own
 * text (a provider message, "the model's answer is not JSON"): never shown. Each refusal maps to
 * one kind; the kind has a short title here and its explanation is a Guide entry
 * (`describe_failure_<kind>`, ADR 0051). Pure.
 */
import { ApiError } from '@/shared/api';

import type { TermRef } from './labels';

export type DraftFailureKind = 'off' | 'unavailable' | 'busy' | 'refused';

export interface DraftFailure {
  kind: DraftFailureKind;
  /** The short lead of the message. */
  title: string;
  /** The Guide term that explains it (an `InfoButton` beside the title). */
  help: TermRef;
  /** Asking again can work (not when drafting is off). */
  retry: boolean;
}

const FAILURES: Record<DraftFailureKind, Omit<DraftFailure, 'kind'>> = {
  off: {
    title: 'Drafting is off',
    help: { kind: 'term', id: 'describe_failure_off' },
    retry: false,
  },
  unavailable: {
    title: 'The model could not answer',
    help: { kind: 'term', id: 'describe_failure_unavailable' },
    retry: true,
  },
  busy: {
    title: 'Too many drafts',
    help: { kind: 'term', id: 'describe_failure_busy' },
    retry: true,
  },
  refused: {
    title: 'Could not draft this',
    help: { kind: 'term', id: 'describe_failure_refused' },
    retry: true,
  },
};

/** The API answers 503 with this lead when the site has not turned the text model on. */
const OFF = /^the text model is (?:forced )?off/i;

export function failureKind(error: unknown): DraftFailureKind {
  if (!(error instanceof ApiError)) return 'unavailable'; // the network, or an unreadable reply
  if (error.status === 429) return 'busy';
  if (error.status === 503) return OFF.test(error.detail) ? 'off' : 'unavailable';
  if (error.status === 400 || error.status === 404 || error.status === 409 || error.status === 422)
    return 'refused';
  return 'unavailable';
}

export function draftFailure(error: unknown): DraftFailure {
  const kind = failureKind(error);
  return { kind, ...FAILURES[kind] };
}

/** A request the trader cancelled: no message. */
export function wasCancelled(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}
