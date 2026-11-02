/**
 * The trader's sentence as the one-line preview reads it (C17, `TaggedSentence`): each part's
 * words tagged with its kind and the words between parts (the connectors the server left out)
 * plain, in sentence order, so the spans concatenate to the sentence. The server decides every
 * offset (UTF-16 units, what `slice` counts) and kind; a part without words (kept, unplaced) has
 * no place in the sentence. Pure.
 */
import type { SentenceKind, SentenceSegment } from '@algotrade/ui';

import { partKindLabel } from './labels';
import { partsOf } from './parts';
import type { ScreenDraft } from './review';

const TAG: Record<string, SentenceKind> = {
  applied: 'applied',
  formula: 'formula',
  needs_choice: 'ask',
  not_available: 'gap',
  not_understood: 'gap',
};

export function sentenceSegments(answer: ScreenDraft): readonly SentenceSegment[] {
  const sentence = answer.sentence ?? '';
  const placed = partsOf(answer)
    .filter((part) => part.end > part.start && part.end <= sentence.length)
    .toSorted((a, b) => a.start - b.start);
  const out: SentenceSegment[] = [];
  let at = 0;
  const plain = (to: number) => {
    const text = sentence.slice(at, to).trim();
    if (text) out.push({ id: `plain-${String(at)}`, text, kind: 'plain' });
  };
  for (const part of placed) {
    if (part.start < at) continue; // overlapping: the server never sends it, but stay whole
    plain(part.start);
    out.push({
      id: part.id,
      text: sentence.slice(part.start, part.end),
      kind: TAG[part.kind] ?? 'gap',
      label: partKindLabel(part.kind).label,
    });
    at = part.end;
  }
  plain(sentence.length);
  return out;
}
