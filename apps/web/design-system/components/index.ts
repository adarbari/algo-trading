/**
 * Design-system components, one folder each (components/<Name>/). Built on the primitives and
 * the final tokens (ADR 0011: tokens -> approved mockups -> components -> screens). Copy the folder
 * shape of primitives/Text (the template) and follow .claude/skills/add-ui-component.
 */
export { AppShell, type AppShellProps } from './AppShell';
export { Banner, type BannerProps, type BannerTone } from './Banner';
export { BarList, type BarListItem, type BarListProps } from './BarList';
export { Button, type ButtonProps, type ButtonVariant } from './Button';
export {
  Chart,
  CHART_RANGES,
  type ChartBand,
  type ChartBandTone,
  type ChartEvent,
  type ChartEventKind,
  type ChartLane,
  type ChartLaneSegment,
  type ChartPoint,
  type ChartProps,
  type ChartRange,
  type ChartReferenceLine,
  type ChartValueBand,
  type ChartSeries,
  type ChartTone,
} from './Chart';
export {
  CalendarGrid,
  type CalendarDay,
  type CalendarEvent,
  type CalendarGridProps,
  type CalendarName,
} from './CalendarGrid';
export { Checkbox, type CheckboxProps } from './Checkbox';
export { Chip, type ChipProps } from './Chip';
export { Combobox, type ComboboxOption, type ComboboxProps } from './Combobox';
export {
  DataTable,
  type ColumnWidth,
  type DataTableCellContext,
  type DataTableColumn,
  type DataTableFill,
  type DataTableProps,
  type DataTableSort,
} from './DataTable';
export { Dialog, type DialogProps } from './Dialog';
export { Disclosure, type DisclosureProps } from './Disclosure';
export {
  Distribution,
  type DistributionBin,
  type DistributionMarker,
  type DistributionProps,
} from './Distribution';
export { Drawer, type DrawerProps } from './Drawer';
export { EmptyState, type EmptyStateProps } from './EmptyState';
export {
  EventChip,
  EventDetail,
  EVENT_KINDS,
  EVENT_KIND_NAMES,
  timeText,
  type EventChipProps,
  type EventItem,
  type EventKind,
} from './EventChip';
export { EventTimeline, type EventTimelineProps } from './EventTimeline';
export { ExpiryLadder, type ExpiryLadderProps, type ExpiryRow } from './ExpiryLadder';
export { ExternalLink, type ExternalLinkProps } from './ExternalLink';
export { ErrorState, type ErrorStateProps } from './ErrorState';
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
export {
  IndicatorRow,
  type IndicatorChange,
  type IndicatorRowProps,
  type IndicatorStatus,
} from './IndicatorRow';
export { Input, type InputProps } from './Input';
export { Kbd, type KbdProps } from './Kbd';
export { LoginForm, type LoginCredentials, type LoginFormProps } from './LoginForm';
export { KeyValue, type KeyValueItem, type KeyValueProps } from './KeyValue';
export { Legend, type DataTone, type LegendItem, type LegendProps } from './Legend';
export {
  LinkedText,
  splitTerms,
  type LinkedTerm,
  type LinkedTextPart,
  type LinkedTextProps,
} from './LinkedText';
export { NavTabs, type NavItem, type NavLinkRenderProps, type NavTabsProps } from './NavTabs';
export { NumberInput, type NumberInputProps } from './NumberInput';
export { OptionList, type OptionListItem, type OptionListProps } from './OptionList';
export { Panel, type PanelProps, type PanelState } from './Panel';
export {
  Popover,
  type PopoverPlacement,
  type PopoverProps,
  type PopoverTriggerProps,
} from './Popover';
export {
  ScoreMeter,
  type ScoreDirection,
  type ScoreMeterProps,
  type ScoreThreshold,
} from './ScoreMeter';
export { SearchInput, type SearchInputProps } from './SearchInput';
export {
  SegmentedControl,
  type SegmentedControlProps,
  type SegmentedOption,
} from './SegmentedControl';
export { Select, type SelectOption, type SelectProps } from './Select';
export { ShareBar, type ShareBarProps } from './ShareBar';
export { Skeleton, type SkeletonProps } from './Skeleton';
export { SourceLine, type SourceLineItem, type SourceLineProps } from './SourceLine';
export { SortableList, type SortableItemState, type SortableListProps } from './SortableList';
export { Sparkline, type SparklineProps, type SparklineTone } from './Sparkline';
export { StackedBar, type StackedBarProps, type StackedBarSegment } from './StackedBar';
export { StatStrip, type StatItem, type StatStripProps } from './StatStrip';
export { StatusBadge, type StatusBadgeProps, type StatusTone } from './StatusBadge';
export { Tabs, type TabItem, type TabsProps } from './Tabs';
export { TickerTag, type TickerTagProps } from './TickerTag';
export {
  Toast,
  ToastProvider,
  useToast,
  type ToastAction,
  type ToastApi,
  type ToastOptions,
  type ToastProps,
  type ToastProviderProps,
  type ToastTone,
} from './Toast';
export { Tooltip, type TooltipProps, type TooltipTriggerProps } from './Tooltip';
export { TopBar, type TopBarProps } from './TopBar';
export { WorkspaceSwitch, type WorkspaceSwitchProps } from './WorkspaceSwitch';
