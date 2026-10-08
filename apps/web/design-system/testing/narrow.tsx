/**
 * The `narrow` story decorator: renders the story inside a 375 px wide size container (a phone),
 * for the `Narrow` story every component with a container query or a narrow tree exports.
 */
import type { Decorator } from '@storybook/react-vite';

import styles from './narrow.module.css';

export const narrow: Decorator = (Story) => (
  <div className={styles.frame} data-testid="narrow-frame">
    <Story />
  </div>
);
