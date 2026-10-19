/**
 * Guide prose as the server sends it: segments of plain text and catalogue names. A name is a
 * link to the field's Guide page and a source marker a raised `[n]` (the label built from the segment’s `source` number, not its text) to the entry `s<n>` of the
 * page's source list; the words are rendered exactly as written, never composed in the browser.
 */
import { LinkedProse, type FontSize, type LinkedProsePart, type TextTone } from '@algotrade/ui';

import { fieldPath } from '../model/paths';

/**
 * The shape of `GuideProse` in the read model (`segments`; `field` set for a catalogue name,
 * `source` for a source marker: the 1-based number of the page's source it cites).
 */
export interface GuideProseValue {
  segments: readonly { text: string; field?: string | null; source?: number | null }[];
}

/** The anchor of the n-th source of a page's source list (`SourceList` ids). */
export function sourceAnchor(n: number): string {
  return `s${String(n)}`;
}

/** Segments as link parts: a catalogue name points at its field page, a marker at its source. */
export function proseParts(prose: GuideProseValue): LinkedProsePart[] {
  return prose.segments.map((segment): LinkedProsePart => {
    if (segment.source !== null && segment.source !== undefined) {
      return {
        text: `[${String(segment.source)}]`,
        href: `#${sourceAnchor(segment.source)}`,
        cite: true,
      };
    }
    return segment.field
      ? { text: segment.text, href: fieldPath(segment.field) }
      : { text: segment.text };
  });
}

export interface GuideProseProps {
  prose: GuideProseValue;
  tone?: TextTone;
  size?: FontSize;
}

export function GuideProse({ prose, tone, size }: GuideProseProps) {
  return (
    <LinkedProse
      parts={proseParts(prose)}
      monoLinks
      {...(tone === undefined ? {} : { tone })}
      {...(size === undefined ? {} : { size })}
    />
  );
}
