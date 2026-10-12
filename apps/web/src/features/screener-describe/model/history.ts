/**
 * The trader's own earlier asks for a missing feature, matched to what a draft lists as missing.
 * The server sends only the viewer's own rows (never another trader's, never a count across
 * users); this matches one to a missing item by its key (a backlog key, else the slug of a
 * request not yet mapped) and says whether there was an ask on an earlier day (the server's
 * `askedBeforeToday`, by exchange date: a count would read 1 for an earlier ask while the draft's
 * own row is still being written). Pure.
 */
import type { components } from '@/shared/api';

import type { MyFeatureRequest } from '../api/feature-requests';

export type MissingFeature = components['schemas']['MissingFeature'];

/** The ref a draft's missing item is stored under: its backlog key, else its new slug. */
export const missingRef = (item: MissingFeature): string | null => item.key ?? item.new_key_slug;

/** The viewer's own request for `item`, if they have one. */
export function ownRequest(
  item: MissingFeature,
  mine: readonly MyFeatureRequest[],
): MyFeatureRequest | null {
  const ref = missingRef(item);
  return (ref === null ? undefined : mine.find((r) => r.ref === ref)) ?? null;
}

/** The request, when it was asked on an earlier day too; else null. */
export function earlierAsk(
  item: MissingFeature,
  mine: readonly MyFeatureRequest[],
): MyFeatureRequest | null {
  const found = ownRequest(item, mine);
  return found?.askedBeforeToday ? found : null;
}

/** The request's status, if the backlog has moved it (open is the starting point). */
export function requestStatus(
  request: MyFeatureRequest | null | undefined,
): 'OPEN' | 'PROMOTED' | 'WONT_DO' | null {
  const status = request?.status;
  return status === 'OPEN' || status === 'PROMOTED' || status === 'WONT_DO' ? status : null;
}
