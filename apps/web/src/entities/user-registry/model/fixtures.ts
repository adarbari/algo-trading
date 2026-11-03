/** Test builders for the user-registry entity (exported for widget tests). */
import type { Person } from './types';

export const person = (over: Partial<Person> = {}): Person => ({
  id: 'ana',
  name: 'Ana',
  role: 'admin',
  licences: ['personal'],
  scheduled: false,
  pendingProvider: false,
  ...over,
});

export const PEOPLE_FIXTURE: Person[] = [
  person(),
  person({ id: 'tom', name: 'Tom', role: 'trader', licences: [] }),
  person({ id: 'eva', name: 'Eva', role: 'trader', licences: [], pendingProvider: true }),
  person({ id: 'site', name: 'Scheduled site screens', licences: [], scheduled: true }),
];
