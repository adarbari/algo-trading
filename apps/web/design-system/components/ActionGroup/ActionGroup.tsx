/**
 * ActionGroup: a row of actions that are full Buttons where there is room and IconButtons with
 * a Tooltip (the label) when the group's own width is under `sm`, so a sheet on a phone does
 * not wrap three buttons into two rows. A page lists the actions; it never picks the form.
 */
import { Stack } from '../../primitives/Stack';
import { useNarrow } from '../../responsive';
import { Button, type ButtonVariant } from '../Button';
import type { IconName } from '../Icon';
import { IconButton } from '../IconButton';
import { Tooltip } from '../Tooltip';
import styles from './ActionGroup.module.css';

export interface ActionItem {
  id: string;
  /** The button text wide; the accessible name and tooltip narrow. */
  label: string;
  icon: IconName;
  onClick: () => void;
  /** Default `secondary`; narrow, `primary` and `dashed` show as `secondary`. */
  variant?: ButtonVariant;
  disabled?: boolean;
}

export interface ActionGroupProps {
  actions: readonly ActionItem[];
  /** Default `sm`. */
  size?: 'sm' | 'md';
  /** Accessible name of the group (default "Actions"). */
  label?: string;
}

export function ActionGroup({ actions, size = 'sm', label = 'Actions' }: ActionGroupProps) {
  const [ref, narrow] = useNarrow('sm');
  return (
    <div ref={ref} className={styles.root} role="group" aria-label={label}>
      <Stack direction="row" gap={2} align="center" wrap>
        {actions.map((action) => {
          const variant = action.variant ?? 'secondary';
          return narrow ? (
            <Tooltip key={action.id} content={action.label}>
              {(props) => (
                <IconButton
                  {...props}
                  icon={action.icon}
                  label={action.label}
                  size={size}
                  variant={variant === 'ghost' ? 'ghost' : 'secondary'}
                  disabled={action.disabled ?? false}
                  onClick={action.onClick}
                />
              )}
            </Tooltip>
          ) : (
            <Button
              key={action.id}
              size={size}
              icon={action.icon}
              variant={variant}
              disabled={action.disabled ?? false}
              onClick={action.onClick}
            >
              {action.label}
            </Button>
          );
        })}
      </Stack>
    </div>
  );
}
