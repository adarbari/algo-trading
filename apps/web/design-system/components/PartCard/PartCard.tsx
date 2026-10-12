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
import { useEffect, useRef, type KeyboardEvent, type ReactNode } from 'react';

import { Heading, type HeadingLevel } from '../../primitives/Heading';

import { Button } from '../Button';
import { Icon } from '../Icon';
import { Input } from '../Input';
import { Skeleton } from '../Skeleton';
import { StatusBadge, type StatusTone } from '../StatusBadge';
import styles from './PartCard.module.css';

/** How a part was understood: the kinds the server sends. Sets the badge tone and icon. */
export type PartKind = 'applied' | 'formula' | 'needs_choice' | 'not_available' | 'not_understood';

/** Where a part comes from: the trader's words, kept from the screen, or words nothing placed. */
export type PartOrigin = 'words' | 'kept' | 'unplaced';

/** The status tone and icon of each kind: the one place the vocabulary is mapped. */
export const PART_KIND_BADGE: Readonly<
  Record<PartKind, { tone: StatusTone; icon: 'check' | 'alert' | 'info' }>
> = {
  applied: { tone: 'positive', icon: 'check' },
  formula: { tone: 'accent', icon: 'info' },
  needs_choice: { tone: 'warning', icon: 'alert' },
  not_available: { tone: 'neutral', icon: 'info' },
  not_understood: { tone: 'negative', icon: 'alert' },
};

export type PartCardState = 'idle' | 'redrafting' | 'error' | 'disabled';

export interface PartRetype {
  /** The words being edited (controlled). */
  value: string;
  onValueChange: (value: string) => void;
  /** Apply the new words to this part only (Enter). */
  onApply: () => void;
  /** Leave without applying (Escape). */
  onCancel: () => void;
  /** Called after Apply or Cancel: move focus back to the caller's target (the card's retype button). */
  onExitFocus?: (() => void) | undefined;
  /** Accessible name of the input ("Retype this part"). */
  inputLabel: string;
  applyLabel: string;
  cancelLabel: string;
  /** The longest text accepted (the 200-character limit). */
  maxLength?: number | undefined;
  /** Apply is off: empty or unchanged text, or an apply in flight. */
  applyDisabled?: boolean | undefined;
}

export interface PartCardProps {
  /** How the part was understood: sets the badge tone and icon. */
  kind: PartKind;
  /** The badge text ("applied", "not understood"). */
  kindLabel: string;
  /** Where the part comes from; `kept` has no quoted words and shows `keptLabel`. */
  origin?: PartOrigin | undefined;
  /** The marker for a kept part ("kept from your screen"); shown beside the badge. */
  keptLabel?: string | undefined;
  /** The trader's own words, quoted and highlighted; omit for a kept part. */
  words?: string | undefined;
  /** The card's name when it has no words (the kept card: "Kept from your screen"). */
  title?: string | undefined;
  /** Outline level of the card's heading (default 3). */
  headingLevel?: HeadingLevel | undefined;
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
  /** A Guide InfoButton for the kind, shown beside the badge. */
  info?: ReactNode;
  /** `idle`, `redrafting` (this card is being redrafted), `error` (inline retry), `disabled`. */
  state?: PartCardState | undefined;
  /** What is happening while redrafting ("Redrafting this part"): announced and shown once. */
  redraftingLabel: string;
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
  origin = 'words',
  keptLabel,
  words,
  title,
  headingLevel = 3,
  readingLabel,
  reading,
  readingSource = 'model',
  checkReadingLabel,
  rows,
  actions,
  info,
  state = 'idle',
  redraftingLabel,
  errorMessage,
  retryLabel,
  onRetry,
  edited = false,
  editedLabel,
  retype,
}: PartCardProps) {
  const badge = PART_KIND_BADGE[kind];
  const redrafting = state === 'redrafting';
  const disabled = state === 'disabled' || redrafting;
  const trusted = readingSource === 'model';
  const quoted = origin !== 'kept' && words ? words : undefined;
  const name = quoted ?? title ?? words;
  const retypeRef = useRef<HTMLDivElement>(null);
  const retyping = Boolean(retype);

  useEffect(() => {
    if (retyping) retypeRef.current?.querySelector('input')?.focus();
  }, [retyping]);

  const onRetypeKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (!retype) return;
    if (event.key === 'Enter' && !retype.applyDisabled) {
      event.preventDefault();
      retype.onApply();
      retype.onExitFocus?.();
    } else if (event.key === 'Escape') {
      event.preventDefault();
      retype.onCancel();
      retype.onExitFocus?.();
    }
  };

  return (
    <article
      className={styles.card}
      data-kind={kind}
      data-origin={origin}
      data-state={state}
      aria-label={name}
      aria-busy={redrafting || undefined}
    >
      <header className={styles.head}>
        <div className={styles.words}>
          <Heading level={headingLevel} size="base">
            {quoted ? <mark className={styles.quote}>{quoted}</mark> : name}
          </Heading>
        </div>
        <div className={styles.marks}>
          {edited && editedLabel && <span className={styles.edited}>{editedLabel}</span>}
          {origin === 'kept' && keptLabel && <span className={styles.edited}>{keptLabel}</span>}
          <StatusBadge tone={badge.tone} icon={badge.icon}>
            {kindLabel}
          </StatusBadge>
          {info}
        </div>
      </header>

      {retype && (
        <div className={styles.retype} ref={retypeRef} inert={disabled}>
          <Input
            aria-label={retype.inputLabel}
            value={retype.value}
            onValueChange={retype.onValueChange}
            maxLength={retype.maxLength}
            onKeyDown={onRetypeKey}
            disabled={disabled}
          />
          <div className={styles.retypeActions}>
            <Button
              variant="primary"
              size="sm"
              disabled={disabled || retype.applyDisabled === true}
              onClick={() => {
                retype.onApply();
                retype.onExitFocus?.();
              }}
            >
              {retype.applyLabel}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              disabled={disabled}
              onClick={() => {
                retype.onCancel();
                retype.onExitFocus?.();
              }}
            >
              {retype.cancelLabel}
            </Button>
          </div>
        </div>
      )}

      {redrafting ? (
        <div className={styles.body}>
          <Skeleton variant="text" lines={2} label={redraftingLabel} />
          <span className={styles.muted} aria-hidden="true">
            {redraftingLabel}
          </span>
        </div>
      ) : (
        <div className={styles.body} data-disabled={disabled || undefined} inert={disabled}>
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
