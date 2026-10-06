/**
 * SourceLine: a muted one-liner naming where a figure comes from: "Source: FRED NFCI · weekly",
 * each source an ExternalLink (the label) with its update cadence in plain text after a middle
 * dot; several sources read "Sources: A · weekly   B · monthly" (a wider gap between them) and wrap. A list of none renders
 * nothing. Sits under a chart, meter or indicator row, in the small muted size.
 */
import { Text } from '../../primitives/Text';
import { ExternalLink } from '../ExternalLink';
import styles from './SourceLine.module.css';

export interface SourceLineItem {
  /** What the source is ("Chicago Fed NFCI"): the link text. */
  label: string;
  /** How often it updates ("weekly", "daily, after the close"): written after the label. */
  cadence?: string;
  /** The source's page (an absolute http(s) URL). */
  url: string;
}

export interface SourceLineProps {
  /** One or more sources, in the order to read them. */
  sources: readonly SourceLineItem[];
}

export function SourceLine({ sources }: SourceLineProps) {
  if (sources.length === 0) return null;
  return (
    <p className={styles.root}>
      <Text size="sm" tone="muted">
        {sources.length === 1 ? 'Source:' : 'Sources:'}
      </Text>
      {sources.map((source) => (
        <span key={`${source.url}-${source.label}`} className={styles.source}>
          <ExternalLink size="sm" href={source.url}>
            {source.label}
          </ExternalLink>
          {source.cadence !== undefined && (
            <Text size="sm" tone="muted">{`· ${source.cadence}`}</Text>
          )}
        </span>
      ))}
    </p>
  );
}
