/** How the Users page words the registry's keys. Labels only: what a term means is a Guide entry. */
import type { Person } from './types';

export const TERM_OF_PERSON = 'user_person';
export const TERM_OF_ROLE = 'user_role';
export const TERM_OF_LICENCES = 'user_licences';
export const TERM_OF_ONBOARD = 'user_onboard';
export const TERM_OF_PENDING_PROVIDER = 'user_pending_provider';
export const TERM_OF_DECLARED_BY_IDENTITY = 'user_declared_by_identity';

/** The remaining provider step the server names by a fixed id; the id is its Guide term. */
export const PROVIDER_STEP_TERMS: Readonly<Record<string, string>> = {
  supabase_add_user: 'user_supabase_step',
};

/** The id a new user takes: 1-64 of a-z, 0-9, `_` and `-` (the server checks it again). */
export const isUserId = (id: string) => /^[a-z0-9_-]{1,64}$/.test(id);

export const roleLabel = (role: string) => (role === 'admin' ? 'Admin' : 'Trader');

/** The licences a person holds, comma-joined; an empty list is the open data only. */
export const licencesText = (person: Person) =>
  person.licences.length === 0 ? '—' : person.licences.join(', ');
