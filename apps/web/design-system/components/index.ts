/**
 * Design-system components, one folder each (components/<Name>/). Built on the primitives and
 * the final tokens (ADR 0011: tokens -> approved mockups -> components -> screens). Copy the folder
 * shape of primitives/Text (the template) and follow .claude/skills/add-ui-component.
 */
export { AppShell, type AppShellProps } from './AppShell';
export { BarList, type BarListItem, type BarListProps } from './BarList';
export { Button, type ButtonProps, type ButtonVariant } from './Button';
export { Checkbox, type CheckboxProps } from './Checkbox';
export { Chip, type ChipProps } from './Chip';
export { Combobox, type ComboboxOption, type ComboboxProps } from './Combobox';
export {
  DataTable,
  type ColumnWidth,
  type DataTableCellContext,
  type DataTableColumn,
  type DataTableProps,
  type DataTableSort,
} from './DataTable';
export { Disclosure, type DisclosureProps } from './Disclosure';
export { Field, type FieldProps } from './Field';
export {
  HeatGrid,
  type HeatGridCell,
  type HeatGridColumn,
  type HeatGridPosition,
  type HeatGridProps,
  type HeatGridRow,
  type HeatStatus,
} from './HeatGrid';
export { Icon, ICON_NAMES, type IconName, type IconProps, type IconTone } from './Icon';
export { IconButton, type IconButtonProps } from './IconButton';
export { Input, type InputProps } from './Input';
export { KeyValue, type KeyValueItem, type KeyValueProps } from './KeyValue';
export { Legend, type DataTone, type LegendItem, type LegendProps } from './Legend';
export { NavTabs, type NavItem, type NavLinkRenderProps, type NavTabsProps } from './NavTabs';
export { NumberInput, type NumberInputProps } from './NumberInput';
export { Panel, type PanelProps, type PanelState } from './Panel';
export { SearchInput, type SearchInputProps } from './SearchInput';
export {
  SegmentedControl,
  type SegmentedControlProps,
  type SegmentedOption,
} from './SegmentedControl';
export { Select, type SelectOption, type SelectProps } from './Select';
export { ShareBar, type ShareBarProps } from './ShareBar';
export { StackedBar, type StackedBarProps, type StackedBarSegment } from './StackedBar';
export { StatStrip, type StatItem, type StatStripProps } from './StatStrip';
export { StatusBadge, type StatusBadgeProps, type StatusTone } from './StatusBadge';
export { Tabs, type TabItem, type TabsProps } from './Tabs';
export { TickerTag, type TickerTagProps } from './TickerTag';
export { TopBar, type TopBarProps } from './TopBar';
export { WorkspaceSwitch, type WorkspaceSwitchProps } from './WorkspaceSwitch';
