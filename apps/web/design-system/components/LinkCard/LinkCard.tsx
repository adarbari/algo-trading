/**
 * LinkCard: a tile that links to one page: a kicker (the question it answers), the title as the
 * link (the whole tile is its click target), a description, an example line and a `footer` for
 * a row of pills (counts, states). Tiles sit in a `Grid` with `collapse`. The link goes through
 * the app's router link (`LinkProvider`), so the design system stays router-free.
 */
import type { ReactNode } from 'react';

import { Heading, type HeadingLevel } from '../../primitives/Heading';
import { Text } from '../../primitives/Text';
import { useRenderLink } from '../TextLink';
import styles from './LinkCard.module.css';

export interface LinkCardProps {
  /** An in-app path or anchor. */
  href: string;
  /** The page's name: the link text. */
  title: string;
  /** The question the page answers, small and muted above the title. */
  kicker?: string | undefined;
  /** What the page is about, a sentence or two. */
  description?: string | undefined;
  /** A marker for the example line ("e.g."); shown before `example`. */
  exampleLabel?: string | undefined;
  /** An example, one line, muted. */
  example?: string | undefined;
  /** Outline level of the title (default 3). */
  headingLevel?: HeadingLevel | undefined;
  /** A row of pills under the text, composed by the caller (StatusBadge, Chip). */
  footer?: ReactNode | undefined;
}

export function LinkCard({
  href,
  title,
  kicker,
  description,
  exampleLabel,
  example,
  headingLevel = 3,
  footer,
}: LinkCardProps) {
  const render = useRenderLink();
  return (
    <article className={styles.card}>
      {kicker !== undefined && (
        <Text size="sm" tone="muted">
          {kicker}
        </Text>
      )}
      <Heading level={headingLevel}>
        {render({
          href,
          className: styles.link ?? '',
          'aria-current': undefined,
          'data-active': undefined,
          children: title,
        })}
      </Heading>
      {description !== undefined && (
        <Text as="p" tone="secondary">
          {description}
        </Text>
      )}
      {example !== undefined && (
        <Text as="p" size="sm" tone="muted">
          {exampleLabel !== undefined ? `${exampleLabel} ${example}` : example}
        </Text>
      )}
      {footer !== undefined && <div className={styles.footer}>{footer}</div>}
    </article>
  );
}
