/** Entity: the ranked missing-feature requests for the Admin Feature requests page (ADR 0066; Admin only). */
export { useFeatureRequests } from './api/queries';
export { REQUESTS_FIXTURE, request as requestFixture } from './model/fixtures';
export {
  isRequestStatus,
  START_PAGE,
  STATUS_LABEL,
  STATUSES,
  statusLabel,
  statusTone,
  TERM_OF_FEASIBILITY,
  TERM_OF_SCORE,
  TERM_OF_STATUS,
  TERM_OF_UNMAPPED,
  type RequestStatus,
} from './model/labels';
export type { FeatureRequest, FeatureRequestList } from './model/types';
