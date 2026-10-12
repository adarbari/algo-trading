/**
 * PartCard: one part of the trader's sentence in the Describe it review. The header quotes the
 * trader's own words (highlighted) with a kind badge (applied, formula to review, needs your call,
 * not available yet, not understood, kept from your screen); under it "We read this as: ..." in
 * plain language, then the part's `rows` (criteria, formula, readings, suggestions) and its
 * `actions` (pick another reading, retype this part). A reading the model did not write (a
 * server-built text, or none) shows a muted "check this reading" note instead of claiming it.
 * The card is a state machine of its own: `idle`, `redrafting` (this card only, the words stay
 * visible), `error` (an inline retry), `disabled`; `edited` marks hand-edited rows; `retype`
 * turns the words into an input with Apply / Cancel. The `kept` kind has no quoted words (a
 * `title` names it). It holds callbacks and slots only: every label and sentence arrives as a
 * prop, the rows component is composed by the caller, and nothing here calls an API.
 */
import { useId, type ReactNode } from 'react';

import { Button } from '../Button';
import { Icon } from '../Icon';
import { Input } from '../Input';
import { Skeleton } from '../Skeleton';
import { StatusBadge, type StatusTone } from '../StatusBadge';
import styles from './PartCard.module.css';

/** How a part was understood; the shared vocabulary of the review (badge and underline kinds). */
export type PartKind = 'applied' | 'formula' | 'ask' | 'gap' | 'not-understood' | 'kept';

/** The status tone and icon of each kind: the one place the vocabulary is mapped. */
export const PART_KIND_BADGE: Readonly<
  Record<PartKind, { tone: StatusTone; icon: 'check' | 'alert' | 'info' }>
> = {
  applied: { tone: 'positive', icon: 'check' },
  formula: { tone: 'accent', icon: 'info' },
  ask: { tone: 'warning', icon: 'alert' },
  gap: { tone: 'neutral', icon: 'info' },
  'not-understood': { tone: 'negative', icon: 'alert' },
  kept: { tone: 'info', icon: 'info' },
};

export type PartCardState = 'idle' | 'redrafting' | 'error' | 'disabled';

export interface PartRetype {
  /** The words being edited (controlled). */
  value: string;
  onValueChange: (value: string) => void;
  /** Apply the new words to this part only. */
  onApply: () => void;
  onCancel: () => void;
  /** Accessible name of the input ("Retype this part"). */
  inputLabel: string;
  applyLabel: string;
  cancelLabel: string;
}

export interface PartCardProps {
  /** How the part was understood: sets the badge tone and icon. */
  kind: PartKind;
  /** The badge text ("applied", "not understood"). */
  kindLabel: string;
  /** The trader's own words, quoted and highlighted; omit for `kept`. */
  words?: string | undefined;
  /** The card's name when it has no words (the `kept` card: "Kept from your screen"). */
  title?: string | undefined;
  /** The lead-in to the reading ("We read this as"). */
  readingLabel?: string | undefined;
  /** The part in plain language. */
  reading?: ReactNode;
  /** Who wrote the reading: `model` is shown as is; `server` or null shows the muted note. */
  readingSource?: 'model' | 'server' | null | undefined;
  /** The muted note for a reading not written by the model ("check this reading"). */
  checkReadingLabel?: string | undefined;
  /** The part's criteria / formula / readings / suggestions, composed by the caller. */
  rows?: ReactNode;
  /** Pick another reading, retype this part: buttons or a picker, composed by the caller. */
  actions?: ReactNode;
  /** `idle`, `redrafting` (this card is being redrafted), `error` (inline retry), `disabled`. */
  state?: PartCardState | undefined;
  /** Text while redrafting ("Redrafting this part"). */
  redraftingLabel?: string | undefined;
  /** What went wrong, shown inline in the `error` state. */
  errorMessage?: string | undefined;
  /** The retry button's label ("Try again"). */
  retryLabel?: string | undefined;
  onRetry?: (() => void) | undefined;
  /** The rows were edited by hand. */
  edited?: boolean | undefined;
  /** The mark's text ("edited"). */
  editedLabel?: string | undefined;
  /** Retype mode: the words become an input with Apply / Cancel. */
  retype?: PartRetype | undefined;
}

export function PartCard({
  kind,
  kindLabel,
  words,
  title,
  readingLabel,
  reading,
  readingSource = 'model',
  checkReadingLabel,
  rows,
  actions,
  state = 'idle',
  redraftingLabel,
  errorMessage,
  retryLabel,
  onRetry,
  edited = false,
  editedLabel,
  retype,
}: PartCardProps) {
  const headingId = useId();
  const badge = PART_KIND_BADGE[kind];
  const redrafting = state === 'redrafting';
  const disabled = state === 'disabled' || redrafting;
  const trusted = readingSource === 'model';
  const name = words ?? title;

  return (
    <article
      className={styles.card}
      data-kind={kind}
      data-state={state}
      aria-labelledby={headingId}
      aria-busy={redrafting || undefined}
    >
      <header className={styles.head}>
        <div id={headingId} className={styles.words}>
          {retype ? (
            <div className={styles.retype}>
              <Input
                aria-label={retype.inputLabel}
                value={retype.value}
                onValueChange={retype.onValueChange}
              />
              <div className={styles.retypeActions}>
                <Button variant="primary" size="sm" onClick={retype.onApply}>
                  {retype.applyLabel}
                </Button>
                <Button variant="ghost" size="sm" onClick={retype.onCancel}>
                  {retype.cancelLabel}
                </Button>
              </div>
            </div>
          ) : words ? (
            <mark className={styles.quote}>{words}</mark>
          ) : (
            <span className={styles.title}>{name}</span>
          )}
        </div>
        <div className={styles.marks}>
          {edited && editedLabel && <span className={styles.edited}>{editedLabel}</span>}
          <StatusBadge tone={badge.tone} icon={badge.icon}>
            {kindLabel}
          </StatusBadge>
        </div>
      </header>

      {redrafting ? (
        <div className={styles.body}>
          <Skeleton variant="text" lines={2} label={redraftingLabel ?? 'Redrafting…'} />
          {redraftingLabel && <span className={styles.muted}>{redraftingLabel}</span>}
        </div>
      ) : (
        <div className={styles.body} data-disabled={disabled || undefined}>
          {(reading || !trusted) && (
            <p className={styles.reading}>
              {readingLabel && <span className={styles.lead}>{readingLabel}: </span>}
              {reading}
              {!trusted && checkReadingLabel && (
                <span className={styles.check}> {checkReadingLabel}</span>
              )}
            </p>
          )}
          {state === 'error' && (
            <div className={styles.error} role="alert">
              <Icon name="alert" size="sm" tone="negative" />
              <span>{errorMessage}</span>
              {onRetry && retryLabel && (
                <Button variant="secondary" size="sm" onClick={onRetry}>
                  {retryLabel}
                </Button>
              )}
            </div>
          )}
          {rows && <div className={styles.rows}>{rows}</div>}
          {actions && <div className={styles.actions}>{actions}</div>}
        </div>
      )}
    </article>
  );
}
