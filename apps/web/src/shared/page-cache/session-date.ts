/**
 * The date of the session the API reads now (`Query.session`), the one stamp the app has of
 * what the nightly run published: the saved page cache is valid for exactly one such date.
 */
import { gql, graphql } from '@/shared/api';

const SessionDateQuery = graphql(`
  query SessionDate {
    session {
      date
    }
  }
`);

/** The session's date, or null when nothing is stored yet. */
export async function fetchSessionDate(): Promise<string | null> {
  return (await gql(SessionDateQuery, {})).session?.date ?? null;
}
