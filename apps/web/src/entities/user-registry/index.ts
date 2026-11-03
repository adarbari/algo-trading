/** Entity: the declared people for the Admin Users page (ADR 0040; Admin only). */
export { useOnboardUser, type OnboardInput } from './api/onboard';
export { useUserRegistry } from './api/queries';
export { PEOPLE_FIXTURE, person as personFixture } from './model/fixtures';
export {
  isUserId,
  licencesText,
  PROVIDER_STEP_TERMS,
  roleLabel,
  TERM_OF_DECLARED_BY_IDENTITY,
  TERM_OF_LICENCES,
  TERM_OF_ONBOARD,
  TERM_OF_PENDING_PROVIDER,
  TERM_OF_PERSON,
  TERM_OF_ROLE,
} from './model/labels';
export type { Person, UserRegistry } from './model/types';
