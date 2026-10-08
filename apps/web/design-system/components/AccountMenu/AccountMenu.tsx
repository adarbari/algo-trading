/**
 * AccountMenu: the top bar's account control: a ghost button with the viewer's name that opens
 * a small Popover holding what belongs to the account rather than to a workspace: the
 * workspace choice (a `WorkspaceSwitch` from the app, admins only; a trader sees none) and
 * "Sign out" when the app gives `onSignOut`. Keeps the workspace switch out of the bar's prime
 * space (owner decision 2026-10-07): the bar shows the brand, the Guide, the status chips and
 * the name; the workspace is chosen here, by the account that may enter it.
 */
import type { ReactNode } from 'react';

import { Divider } from '../../primitives/Divider';
import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import { Button } from '../Button';
import { Popover } from '../Popover';
import styles from './AccountMenu.module.css';

export interface AccountMenuProps {
  /** The viewer's name (the trigger's text). */
  name: string;
  /** The menu's content: the workspace switch, settings links. Nothing: only "Sign out". */
  children?: ReactNode;
  /** Shown as a "Sign out" button at the end of the menu; absent: no sign-out (auth off). */
  onSignOut?: () => void;
}

export function AccountMenu({ name, children, onSignOut }: AccountMenuProps) {
  return (
    <Popover
      label="Account"
      placement="bottom-end"
      trigger={(props) => (
        <span className={styles.trigger}>
          <Button {...props} variant="ghost" size="sm" iconEnd="chevron-down" fullWidth>
            {name}
          </Button>
        </span>
      )}
    >
      <div className={styles.menu}>
        <Stack gap={3}>
          <Text size="sm" tone="muted">
            Signed in as {name}
          </Text>
          {children}
          {onSignOut ? (
            <>
              <Divider />
              <Button variant="ghost" size="sm" onClick={onSignOut}>
                Sign out
              </Button>
            </>
          ) : null}
        </Stack>
      </div>
    </Popover>
  );
}
