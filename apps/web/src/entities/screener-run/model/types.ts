/** The screener-run entity's types: the server's runs and one run's record, as the operations select. */
import type { gqlTypes } from '@/shared/api';

export type ScreenerRunSummary = gqlTypes.AdminScreenerRunsQuery['screenerRuns'][number];
export type ScreenerRunRecord = NonNullable<gqlTypes.AdminScreenerRunQuery['screenerRun']>;
export type ScreenerRunDecision = NonNullable<ScreenerRunRecord['decisions']>[number];
