/**
 * The trader's sentence as tagged spans (the TaggedSentence segments): where the server named a
 * piece of the sentence (an unresolved term, a missing field, a formula), find it in the text and
 * tag it; the words between stay plain. Presentation only: the server decides what a span is, this
 * only finds where it sits (exact match first, then ignoring case), skips a span it cannot find
 * and lets the earlier of two overlapping spans win. Pure.
 */
import type { SentenceSegment } from '@algotrade/ui';

export type TagKind = Exclude<SentenceSegment['kind'], 'plain'>;

/** The short label shown beside a tagged span: text as well as underline, never colour alone. */
export const TAG_LABELS: Record<TagKind, string> = {
  applied: 'applied',
  formula: 'formula',
  ask: 'needs your call',
  gap: 'not available yet',
};

export interface SpanTag {
  /** The piece of the sentence, as the server gave it. */
  span: string;
  kind: TagKind;
}

function locate(text: string, span: string): { start: number; end: number } | null {
  if (span === '') return null;
  let start = text.indexOf(span);
  if (start < 0) start = text.toLowerCase().indexOf(span.toLowerCase());
  return start < 0 ? null : { start, end: start + span.length };
}

/** The sentence cut into plain and tagged segments, in order; they read back as the sentence. */
export function tagSentence(text: string, tags: readonly SpanTag[]): SentenceSegment[] {
  const found = tags
    .map((tag, order) => ({ tag, order, at: locate(text, tag.span) }))
    .flatMap((f) => (f.at ? [{ ...f, ...f.at }] : []))
    .sort((a, b) => a.start - b.start || a.order - b.order);
  const segments: SentenceSegment[] = [];
  const plain = (from: number, to: number) => {
    const words = text.slice(from, to).trim();
    if (words !== '') segments.push({ id: `plain-${String(from)}`, text: words, kind: 'plain' });
  };
  let cursor = 0;
  for (const { tag, start, end } of found) {
    if (start < cursor) continue; // overlaps an earlier span
    plain(cursor, start);
    segments.push({
      id: `${tag.kind}-${String(start)}`,
      text: text.slice(start, end),
      kind: tag.kind,
      label: TAG_LABELS[tag.kind],
    });
    cursor = end;
  }
  plain(cursor, text.length);
  return segments;
}
