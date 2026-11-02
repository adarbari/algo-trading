/** Entity: the declared people for the Admin Users page (ADR 0040; Admin only). */
export { useUserRegistry } from './api/queries';
export { PEOPLE_FIXTURE, person as personFixture } from './model/fixtures';
export {
  licencesText,
  roleLabel,
  TERM_OF_LICENCES,
  TERM_OF_PERSON,
  TERM_OF_ROLE,
} from './model/labels';
export type { Person, UserRegistry } from './model/types';
