/**
 * LinkedProse: a paragraph given as parts, some of them links to pages of this app (a field's
 * Guide page inside a caveat): a part with an `href` is a TextLink (the app's router link, so
 * the design system stays router-free), the rest is plain Text in the chosen tone and size. The
 * parts come split from the server (it cuts the sentence at the names it mentions); the
 * caller maps each part to an address. Links to other sites are LinkedText's.
 */
import type { FontSize } from '../../tokens';
import { Text, type TextTone } from '../../primitives/Text';
import { TextLink } from '../TextLink';
import styles from './LinkedProse.module.css';

export interface LinkedProsePart {
  /** The words, exactly as they read in the paragraph (put the spaces in them). */
  text: string;
  /** Present for a link: an in-app path ("/guide/fields/rel_volume"). */
  href?: string;
}

export interface LinkedProseProps {
  /** The paragraph in order; the parts are joined as written. */
  parts: readonly LinkedProsePart[];
  /** Colour role of the plain text, as on Text. */
  tone?: TextTone;
  /** Type-scale step, as on Text; the links take the same size. */
  size?: FontSize;
  /** Set the links in the mono face (they are catalogue names). */
  monoLinks?: boolean;
}

export function LinkedProse({
  parts,
  tone = 'default',
  size = 'base',
  monoLinks = false,
}: LinkedProseProps) {
  return (
    <span className={styles.root}>
      <Text tone={tone} size={size}>
        {parts.map((part, index) =>
          part.href === undefined ? (
            part.text
          ) : (
            <TextLink
              key={`${String(index)}-${part.href}`}
              href={part.href}
              size="inherit"
              mono={monoLinks}
            >
              {part.text}
            </TextLink>
          ),
        )}
      </Text>
    </span>
  );
}
