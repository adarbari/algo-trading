/**
 * What the unsaved criteria would change: the live preview's picks against the screener's saved
 * run of the same session, as "+N enter" and "-N leave" with the tickers. The server compares
 * them over every row (the preview's `changes`); this only says it. Shown only while the
 * Builder holds unsaved changes and the screener has a saved run for the preview's session.
 */
import { Banner, Button } from '@algotrade/ui';
import { useEffect } from 'react';

import { useScreenerBuilder } from '@/features/screener-builder';

export interface PreviewDiffProps {
  /** Review the criteria (shown when the diff is outside the editor). */
  onReview?: () => void;
}

const names = (symbols: readonly string[]) => symbols.join(', ');

/** The changes the unsaved criteria would make (null: nothing unsaved, or nothing to compare). */
export function usePreviewChanges() {
  const builder = useScreenerBuilder();
  const changes = builder.preview.data?.changes;
  if (!builder.dirty || !changes) return null;
  return changes;
}

/** Tells the page which saved picks the unsaved criteria would drop (for the results grid). */
export function PreviewChangesReporter({
  onChange,
}: {
  onChange: (leaving: ReadonlySet<string>) => void;
}) {
  const changes = usePreviewChanges();
  const leaving = changes?.left.join(',') ?? '';
  useEffect(() => {
    onChange(new Set(leaving === '' ? [] : leaving.split(',')));
    return () => {
      onChange(new Set());
    };
  }, [leaving, onChange]);
  return null;
}

export function PreviewDiff({ onReview }: PreviewDiffProps) {
  const changes = usePreviewChanges();
  if (!changes) return null;
  const { entered, left } = changes;
  const message =
    entered.length === 0 && left.length === 0
      ? 'The same tickers are picked.'
      : [
          `+${String(entered.length)} enter${entered.length > 0 ? `: ${names(entered)}` : ''}.`,
          `-${String(left.length)} leave${left.length > 0 ? `: ${names(left)}` : ''}.`,
        ].join(' ');
  return (
    <Banner
      tone="info"
      title={`Unsaved changes: preview against the saved run of ${changes.session}`}
      actions={
        onReview ? (
          <Button size="sm" onClick={onReview}>
            Review criteria
          </Button>
        ) : undefined
      }
    >
      {message}
    </Banner>
  );
}
