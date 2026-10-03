/**
 * WorkspaceSwitch: the top bar's switch between workspaces (Trader / Admin), a SegmentedControl
 * named "Workspace". Selecting a workspace calls `onValueChange`; the app navigates (the design
 * system knows no routes). Role gating stays in the app: pass only the workspaces the user may
 * enter.
 */
import { SegmentedControl, type SegmentedOption } from '../SegmentedControl';
import styles from './WorkspaceSwitch.module.css';

export interface WorkspaceSwitchProps<V extends string = string> {
  /** The workspaces the user may enter, in order (e.g. Trader, Admin). */
  workspaces: readonly SegmentedOption<V>[];
  /** The current workspace. */
  value: V;
  /** Called with the chosen workspace; the app navigates to its home. */
  onValueChange: (value: V) => void;
  /** Accessible name of the switch; "Workspace" by default. */
  label?: string;
}

export function WorkspaceSwitch<V extends string = string>({
  workspaces,
  value,
  onValueChange,
  label = 'Workspace',
}: WorkspaceSwitchProps<V>) {
  return (
    <div className={styles.workspaceSwitch}>
      <SegmentedControl
        aria-label={label}
        options={workspaces}
        value={value}
        onValueChange={onValueChange}
      />
    </div>
  );
}
