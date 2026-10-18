/**
 * A screen's draft document basics: a blank one (what a new screener opens with) and a copy of a
 * source without the keys the authoring flow manages, apart from the spec model so the
 * Screeners list (which starts and copies one) does not load the Builder's document code with it.
 */
import { feature } from '@/shared/api';

import type { ScreenDocument } from '../model/spec';

type Table = Record<string, Record<string, unknown>>;

/** The keys the authoring flow manages (a draft never carries them). */
const MANAGED_KEYS = ['version', 'schedule'];

/** A document without the keys the authoring flow manages. */
export function toDocument(source: Readonly<Record<string, unknown>>, id: string): ScreenDocument {
  const kept = Object.fromEntries(
    Object.entries(source).filter(([key]) => key !== 'id' && !MANAGED_KEYS.includes(key)),
  );
  return { id, ...kept };
}

/**
 * Who a new screener screens (ADR 0030): a rule screen has no selection, so it opens with the
 * base gates as criteria. They are ordinary criteria: edit or remove any of them.
 */
const BASE_CRITERIA: Table = {
  security_type: {
    field: feature('instrument.security_type'),
    op: 'in',
    value: ['COMMON_STOCK', 'ADR', 'ETF'],
  },
  status: { field: feature('instrument.status'), op: 'eq', value: 'ACTIVE' },
  optionable: { field: feature('instrument.optionable'), op: 'eq', value: true },
};

/** A blank draft: a rule screen with the base gates. */
export function blankDocument(id: string): ScreenDocument {
  return { id, kind: 'screener', impl: 'rules', criteria: structuredClone(BASE_CRITERIA) };
}
