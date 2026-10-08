/**
 * Guide prose as the server sends it: segments of plain text and catalogue names. A name is a
 * link to the field's Guide page; the words are rendered exactly as written, never composed
 * in the browser.
 */
import { LinkedProse, type FontSize, type LinkedProsePart, type TextTone } from '@algotrade/ui';

import { fieldPath } from '../model/paths';

/** The shape of `GuideProse` in the read model (`segments`; `field` set for a catalogue name). */
export interface GuideProseValue {
  segments: readonly { text: string; field?: string | null }[];
}

/** Segments as link parts: a catalogue name points at its field page. */
export function proseParts(prose: GuideProseValue): LinkedProsePart[] {
  return prose.segments.map((segment) =>
    segment.field ? { text: segment.text, href: fieldPath(segment.field) } : { text: segment.text },
  );
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
