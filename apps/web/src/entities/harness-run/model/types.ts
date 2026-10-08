/** The harness-run entity's types: the server's runs and one run's rows, as the operations select. */
import type { gqlTypes } from '@/shared/api';

export type HarnessRun = gqlTypes.HarnessRunsQuery['harnessRuns'][number];
export type HarnessRunRows = NonNullable<gqlTypes.HarnessRunQuery['harnessRun']>;
export type HarnessLostInput = HarnessRunRows['lostInputs'][number];
export type HarnessRow = HarnessRunRows['rows'][number];
