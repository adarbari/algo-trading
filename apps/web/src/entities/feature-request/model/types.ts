/** The feature-request entity's types: the server's ranked list and its rows, as the operation selects. */
import type { gqlTypes } from '@/shared/api';

export type FeatureRequestList = NonNullable<gqlTypes.FeatureRequestsQuery['featureRequests']>;
export type FeatureRequest = FeatureRequestList['rows'][number];
