/**
 * The calendar's source and the names it gives: the site's scope list (the default) or the
 * latest results of a chosen screener (its picks: one page of up to 1000). The names are the
 * server's; `ready` says whether the calendar can be asked for yet.
 */
import { useState } from 'react';

import {
  DEFAULT_DECISIONS,
  useScreenerResults,
  useScreeners,
  type ScreenerResultsResponse,
} from '@/entities/screen';

/** The source value for the site's scope list. */
export const SCOPE_SOURCE = 'scope';

/** The most names a page of results holds (the API's page cap). */
const PAGE = 1000;

export interface CalendarSource {
  /** `SCOPE_SOURCE` or a screener id. */
  value: string;
  setValue: (value: string) => void;
  /** The screeners that can be chosen. */
  screeners: readonly string[];
  /** Ask for the scope list instead of names. */
  scope: boolean;
  /** The instrument ids of the chosen screener's picks (empty for the scope list). */
  ids: readonly string[];
  /** The calendar can be asked for: the scope list, or a screener with a run and picks. */
  ready: boolean;
  /** Why the calendar cannot be asked for yet ("No run for the session"), else null. */
  message: string | null;
  /** The screener's results are loading. */
  loading: boolean;
  /** The screener's results failed to load. */
  failed: boolean;
}

type Results = ScreenerResultsResponse['screener'];

function idsOf(screener: Results | undefined): string[] {
  return (screener?.latestRun?.results.results ?? []).map((r) => r.instrumentId);
}

export function useCalendarSource(): CalendarSource {
  const [value, setValue] = useState(SCOPE_SOURCE);
  const configs = useScreeners();
  const isScope = value === SCOPE_SOURCE;
  const results = useScreenerResults(
    value,
    { decisions: DEFAULT_DECISIONS, columns: [], size: PAGE },
    !isScope,
  );
  const screener = results.data?.screener;
  const ids = isScope ? [] : idsOf(screener);
  let message: string | null = null;
  if (!isScope && !results.isPending && !results.isError) {
    if (!screener) message = 'This screener is not available.';
    else if (!screener.latestRun)
      message = screener.notRun?.detail || 'This screener has no run for the session.';
    else if (ids.length === 0) message = 'This screener picked no names in its latest run.';
  }
  return {
    value,
    setValue,
    // The user's own screener and a site preset can share an id: each once.
    screeners: [...new Set((configs.data ?? []).map((c) => c.configId))],
    scope: isScope,
    ids,
    ready: isScope || (!results.isPending && !results.isError && message === null),
    message,
    loading: !isScope && results.isPending,
    failed: !isScope && results.isError,
  };
}
