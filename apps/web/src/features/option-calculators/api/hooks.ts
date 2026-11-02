/**
 * The option calculators' preview POSTs (`/preview/options/roll`, `/preview/options/calls`; plan V11).
 * Each is a mutation: the figures a trader types live in the caller's state and the mutation's
 * variables only, never in a query key, the URL or storage, and the response is derived figures
 * priced on the session's end-of-day chain (no bid, ask, last or size). An unknown ticker is a 404
 * the caller shows.
 */
import { useMutation } from '@tanstack/react-query';

import { api, unwrap } from '@/shared/api';

import type { CallsBody, RollBody } from '../model/bodies';

/** The rolls of a sold option (the contract and its optional sold-at price in `body`). */
export function useRollPreview() {
  return useMutation({
    mutationFn: (body: RollBody) => unwrap(api.POST('/preview/options/roll', { body })),
  });
}

/** The calls that could be sold on shares held (shares and the trader's price in `body`). */
export function useCallsPreview() {
  return useMutation({
    mutationFn: (body: CallsBody) => unwrap(api.POST('/preview/options/calls', { body })),
  });
}
