/**
 * LinkedText: a sentence given as parts, some of them links: a part with an `href` is an
 * ExternalLink (real anchor, `rel="noopener"`, visible focus, the external mark and "opens in a
 * new tab" for screen readers), the rest is plain Text in the chosen tone and size. The parts
 * come split from the caller (a server-written sentence arrives already cut); `splitTerms` cuts a
 * sentence at the first occurrence of each term, for stories and tests, and reports the terms it
 * could not place (absent, empty, or overlapping an earlier one) instead of dropping them silently.
 */
import type { FontSize } from '../../tokens';
import { Text, type TextTone } from '../../primitives/Text';
import { ExternalLink } from '../ExternalLink';
import styles from './LinkedText.module.css';

export interface LinkedTextPart {
  /** The words, exactly as they read in the sentence. */
  text: string;
  /** Present for a link: the page's address (an absolute http(s) URL). */
  href?: string;
  /** Hover text about the linked page ("Federal Reserve Bank of St. Louis"). */
  title?: string;
}

export interface LinkedTextProps {
  /** The sentence in order; the parts are joined as written (put the spaces in them). */
  parts: readonly LinkedTextPart[];
  /** Colour role of the plain text, as on Text. */
  tone?: TextTone;
  /** Type-scale step, as on Text; the links take the same size. */
  size?: FontSize;
}

export interface LinkedTerm {
  /** The words to link, exactly as they appear in the sentence ("Sahm rule"). */
  text: string;
  href: string;
  title?: string;
}

/** Cuts `text` into parts, linking the first occurrence of each term (case-sensitive). */
export function splitTerms(
  text: string,
  terms: readonly LinkedTerm[],
): { parts: LinkedTextPart[]; unmatched: string[] } {
  const found: { start: number; end: number; term: LinkedTerm }[] = [];
  const unmatched: string[] = [];
  const candidates = terms
    .map((term) => ({ term, start: term.text === '' ? -1 : text.indexOf(term.text) }))
    .sort((a, b) => a.start - b.start);
  for (const { term, start } of candidates) {
    const last = found.at(-1);
    if (start < 0 || (last !== undefined && start < last.end)) unmatched.push(term.text);
    else found.push({ start, end: start + term.text.length, term });
  }
  const parts: LinkedTextPart[] = [];
  let at = 0;
  for (const { start, end, term } of found) {
    if (start > at) parts.push({ text: text.slice(at, start) });
    parts.push({
      text: term.text,
      href: term.href,
      ...(term.title === undefined ? {} : { title: term.title }),
    });
    at = end;
  }
  if (at < text.length) parts.push({ text: text.slice(at) });
  return { parts, unmatched };
}

export function LinkedText({ parts, tone = 'default', size = 'base' }: LinkedTextProps) {
  return (
    <span className={styles.root}>
      <Text tone={tone} size={size}>
        {parts.map((part, index) =>
          part.href === undefined ? (
            part.text
          ) : (
            <ExternalLink
              key={`${String(index)}-${part.href}`}
              href={part.href}
              size="inherit"
              {...(part.title === undefined ? {} : { title: part.title })}
            >
              {part.text}
            </ExternalLink>
          ),
        )}
      </Text>
    </span>
  );
}
