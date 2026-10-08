/** The usage entity's types: the server's `LlmUsage` read and its parts, as the operation selects. */
import type { gqlTypes } from '@/shared/api';

export type LlmUsage = NonNullable<gqlTypes.LlmUsageQuery['llmUsage']>;
export type UsageWindow = LlmUsage['windows'][number];
export type UsageTally = UsageWindow['tally'];
export type UsageBreakdown = LlmUsage['breakdowns'][number];
export type UsageSlice = UsageBreakdown['rows'][number];
export type UsageDay = LlmUsage['daily'][number];
export type UsageCall = LlmUsage['recent'][number];
export type UsageReliability = LlmUsage['reliability'];
