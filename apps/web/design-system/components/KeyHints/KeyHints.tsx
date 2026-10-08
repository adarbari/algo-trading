/**
 * KeyHints: a row of keyboard shortcuts with what each does ("j k move · c compare · Enter
 * open"), at caption size, under a panel's actions. Hidden under a coarse pointer (a phone or
 * tablet without a keyboard): a shortcut is never the only way to an action, so a touch user
 * loses nothing. Keeps the hint row out of page code: a page lists the hints, never a Kbd.
 */
import { Text } from '../../primitives/Text';
import { Kbd } from '../Kbd';
import styles from './KeyHints.module.css';

export interface KeyHint {
  /** The keys of the action: `['j', 'k']` lists alternatives, each outlined on its own. */
  keys: readonly string[];
  /** What the keys do ("move", "compare", "open in Explore"). */
  label: string;
}

export interface KeyHintsProps {
  hints: readonly KeyHint[];
  /** Accessible name of the list (default "Keyboard shortcuts"). */
  label?: string;
}

export function KeyHints({ hints, label = 'Keyboard shortcuts' }: KeyHintsProps) {
  return (
    <ul className={styles.hints} aria-label={label}>
      {hints.map((hint) => (
        <li key={hint.label} className={styles.hint}>
          {hint.keys.map((key) => (
            <Kbd key={key} keys={[key]} size="xs" />
          ))}
          <Text size="xs" tone="muted">
            {hint.label}
          </Text>
        </li>
      ))}
    </ul>
  );
}
