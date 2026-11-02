/** How the Users page words the registry's keys. Labels only: what a term means is a Guide entry. */
import type { Person } from './types';

export const TERM_OF_PERSON = 'user_person';
export const TERM_OF_ROLE = 'user_role';
export const TERM_OF_LICENCES = 'user_licences';

export const roleLabel = (role: string) => (role === 'admin' ? 'Admin' : 'Trader');

/** The licences a person holds, comma-joined; an empty list is the open data only. */
export const licencesText = (person: Person) =>
  person.licences.length === 0 ? '—' : person.licences.join(', ');
