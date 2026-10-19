/**
 * SourceList: a numbered reading list: per source a kind label ("Academic paper"), the title as
 * an ExternalLink and a one-line "why read it". Each item carries its `id`, so a citation in the
 * text ("[3]") links to it with `#<id>`. Where SourceLine names one figure's source in a line,
 * this is the page's bibliography.
 */
import { Text } from '../../primitives/Text';
import { ExternalLink } from '../ExternalLink';
import styles from './SourceList.module.css';

export interface SourceListItem {
  /** The anchor of the item ("s3"): a citation links to `#s3`. */
  id: string;
  /** What kind of source it is ("Academic paper", "Regulator filing"); omitted when the list does not say. */
  kind?: string;
  /** The reference as written: authors, year, title, journal. The link text. */
  title: string;
  /** The source's page (an absolute http(s) URL). */
  url: string;
  /** Why it is worth reading, one line. */
  why?: string;
}

export interface SourceListProps {
  items: readonly SourceListItem[];
  /** Accessible name of the list ("Sources and further reading"). */
  'aria-label': string;
}

export function SourceList({ items, 'aria-label': ariaLabel }: SourceListProps) {
  if (items.length === 0) return null;
  return (
    <ol className={styles.list} aria-label={ariaLabel}>
      {items.map((item) => (
        <li key={item.id} id={item.id} className={styles.item}>
          {item.kind !== undefined && (
            <Text as="p" size="xs" tone="muted">
              {item.kind}
            </Text>
          )}
          <ExternalLink size="sm" href={item.url}>
            {item.title}
          </ExternalLink>
          {item.why !== undefined && (
            <Text as="p" size="sm" tone="secondary">
              {item.why}
            </Text>
          )}
        </li>
      ))}
    </ol>
  );
}
