/**
 * EventChip: an event's kind as a colour and a shape plus its short label ("Earnings", "NVDA
 * earnings", "CPI", "FOMC", "Opex", "2.02 results"). The kind is never colour alone: each kind
 * has its own glyph (a triangle for earnings, hollow for the reference name's; a circle for a
 * macro release; a square for a market-structure day; a down triangle on a dashed border for a
 * filing) and a screen-reader prefix naming it. Colours are the existing tokens (accent, info,
 * warning, neutral). With `event` the chip is focusable and its tooltip (hover and keyboard
 * focus) gives the label, time, source and the day the event became known; without it the chip
 * is static text. Not a filter: that is Chip.
 */
import { VisuallyHidden } from '../../primitives/VisuallyHidden';
import { Tooltip } from '../Tooltip';
import styles from './EventChip.module.css';
import { EventDetail } from './EventDetail';
import { EVENT_KIND_NAMES, type EventItem, type EventKind } from './eventKinds';

export interface EventChipProps {
  /** What kind of event: sets the colour, the glyph and the screen-reader prefix. */
  kind: EventKind;
  /** The short text ("CPI", "Earnings", "2.02 results"). */
  label: string;
  /** The full event: makes the chip focusable with a details tooltip (label, time, source, known-from). */
  event?: EventItem;
}

function Glyph({ kind }: { kind: EventKind }) {
  return (
    <svg className={styles.glyph} viewBox="0 0 12 12" aria-hidden="true" focusable="false">
      {kind === 'own_earnings' && <path d="M6 1.5 10.5 9.5h-9z" data-fill="solid" />}
      {kind === 'reference_earnings' && <path d="M6 1.5 10.5 9.5h-9z" data-fill="hollow" />}
      {kind === 'macro_release' && <circle cx="6" cy="6" r="4" data-fill="solid" />}
      {kind === 'market_structure' && <rect x="2" y="2" width="8" height="8" data-fill="solid" />}
      {kind === 'filing' && <path d="M6 10.5 1.5 2.5h9z" data-fill="solid" />}
    </svg>
  );
}

export function EventChip({ kind, label, event }: EventChipProps) {
  const content = (
    <>
      <Glyph kind={kind} />
      <VisuallyHidden>{`${EVENT_KIND_NAMES[kind]}: `}</VisuallyHidden>
      <span className={styles.label}>{label}</span>
    </>
  );
  if (!event) {
    return (
      <span className={styles.chip} data-kind={kind}>
        {content}
      </span>
    );
  }
  return (
    <Tooltip content={<EventDetail event={event} />} delay="none">
      {(trigger) => (
        <button
          type="button"
          className={styles.chip}
          data-kind={kind}
          data-interactive=""
          {...trigger}
        >
          {content}
        </button>
      )}
    </Tooltip>
  );
}
