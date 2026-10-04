/** The run entity's types: nightly runs, one run record, its items and the quality checks. */
import type { components } from '@/shared/api';

type Schemas = components['schemas'];

export type NightlyRun = Schemas['NightlyRun'];
export type RunStep = Schemas['Step'];
export type RunDetail = Schemas['RunDetail'];
export type FailureGroup = Schemas['FailureGroup'];
export type RunItem = Schemas['RunItem'];
export type QualityReport = Schemas['QualityReport'];
export type QualityCheck = Schemas['QualityCheck'];
