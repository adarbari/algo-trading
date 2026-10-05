/**
 * What the unsaved criteria would change: the live preview's picks against the saved run's, as
 * "+N enter" and "-N leave" with the tickers. Shown only while the Builder holds unsaved changes
 * and the screener has a saved run to compare with. The preview lists its top rows only, so a
 * longer list of picks is compared by what it shows.
 */
import { Banner, Button } from '@algotrade/ui';
import { useEffect } from 'react';

import { useScreenerBuilder } from '@/features/screener-builder';
import {
  DEFAULT_DECISIONS,
  previewChanges,
  useScreenTable,
  type PickedRow,
} from '@/entities/screen';

export interface PreviewDiffProps {
  /** The screener whose saved run is the baseline. */
  id: string;
  /** Review the criteria (shown when the diff is outside the editor). */
  onReview?: () => void;
}

const names = (symbols: readonly string[]) => symbols.join(', ');

/**
 * The changes the unsaved criteria would make against the saved run, with the sessions compared
 * (null: nothing unsaved, no saved run to compare with, or no preview yet).
 */
export function usePreviewChanges(id: string) {
  const builder = useScreenerBuilder();
  const saved = useScreenTable(id, { decisions: DEFAULT_DECISIONS, columns: [] });
  const preview = builder.preview.data;
  if (!builder.dirty || !saved.data || !preview) return null;
  const savedPicks: PickedRow[] = saved.data.page.items;
  return {
    ...previewChanges(savedPicks, preview.rows),
    previewSession: preview.session,
    savedSession: saved.data.session,
  };
}

/** Tells the page which saved picks the unsaved criteria would drop (for the results grid). */
export function PreviewChangesReporter({
  id,
  onChange,
}: {
  id: string;
  onChange: (leaving: ReadonlySet<string>) => void;
}) {
  const changes = usePreviewChanges(id);
  const leaving = changes?.exit.join(',') ?? '';
  useEffect(() => {
    onChange(new Set(leaving === '' ? [] : leaving.split(',')));
    return () => {
      onChange(new Set());
    };
  }, [leaving, onChange]);
  return null;
}

export function PreviewDiff({ id, onReview }: PreviewDiffProps) {
  const changes = usePreviewChanges(id);
  if (!changes) return null;
  const { enter, exit } = changes;
  const message =
    enter.length === 0 && exit.length === 0
      ? 'The same tickers are picked.'
      : [
          `+${String(enter.length)} enter${enter.length > 0 ? `: ${names(enter)}` : ''}.`,
          `-${String(exit.length)} leave${exit.length > 0 ? `: ${names(exit)}` : ''}.`,
        ].join(' ');
  return (
    <Banner
      tone="info"
      title={`Unsaved changes: preview on ${changes.previewSession}, against the saved run of ${changes.savedSession}`}
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
