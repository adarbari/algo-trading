/**
 * Design-system components, one folder each (components/<Name>/). Built on the primitives and
 * the final tokens (ADR 0011: tokens -> approved mockups -> components -> screens). Copy the folder
 * shape of primitives/Text (the template) and follow .claude/skills/add-ui-component.
 */
export { AccountMenu, type AccountMenuProps } from './AccountMenu';
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
export {
  CauseChain,
  statusTone,
  type CauseChainProps,
  type CauseLevel,
  type CauseLink,
} from './CauseChain';
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
export { ExpandableRow, type ExpandableRowProps } from './ExpandableRow';
export {
  Distribution,
  type DistributionBin,
  type DistributionMarker,
  type DistributionProps,
} from './Distribution';
export { DocLayout, DocSection, type DocLayoutProps, type DocSectionProps } from './DocLayout';
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
export {
  HelpDrawer,
  HelpLead,
  HelpSection,
  type HelpDrawerProps,
  type HelpLeadProps,
  type HelpSectionProps,
} from './HelpDrawer';
export { Icon, ICON_NAMES, type IconName, type IconProps, type IconTone } from './Icon';
export { IconButton, type IconButtonProps } from './IconButton';
export { InfoButton, type InfoButtonProps } from './InfoButton';
export {
  IndicatorRow,
  type IndicatorChange,
  type IndicatorRowProps,
  type IndicatorStatus,
} from './IndicatorRow';
export { Input, type InputProps } from './Input';
export { Kbd, type KbdProps } from './Kbd';
export { FilterBar, type FilterBarProps } from './FilterBar';
export { KeyHints, type KeyHint, type KeyHintsProps } from './KeyHints';
export { NavList, type NavListItem, type NavListProps } from './NavList';
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
export { LinkedProse, type LinkedProsePart, type LinkedProseProps } from './LinkedProse';
export { ActionGroup, type ActionGroupProps, type ActionItem } from './ActionGroup';
export { MasterDetail, type MasterDetailProps } from './MasterDetail';
export { NavTabs, type NavItem, type NavLinkRenderProps, type NavTabsProps } from './NavTabs';
export { NumberInput, type NumberInputProps } from './NumberInput';
export {
  OddsLine,
  type OddsLineNotReady,
  type OddsLineProps,
  type OddsLineReady,
} from './OddsLine';
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
export {
  SearchDialog,
  type SearchDialogGroup,
  type SearchDialogItem,
  type SearchDialogProps,
} from './SearchDialog';
export { SearchInput, type SearchInputProps } from './SearchInput';
export {
  SegmentedControl,
  type SegmentedControlProps,
  type SegmentedOption,
} from './SegmentedControl';
export { SectionNav, type SectionNavItem, type SectionNavProps } from './SectionNav';
export { Select, type SelectOption, type SelectProps } from './Select';
export { ShareBar, type ShareBarProps } from './ShareBar';
export { Skeleton, type SkeletonProps } from './Skeleton';
export { SourceLine, type SourceLineItem, type SourceLineProps } from './SourceLine';
export { SortableList, type SortableItemState, type SortableListProps } from './SortableList';
export { Sparkline, type SparklineProps, type SparklineTone } from './Sparkline';
export { StackedBar, type StackedBarProps, type StackedBarSegment } from './StackedBar';
export { StatStrip, type StatItem, type StatStripProps } from './StatStrip';
export { StatusBadge, type StatusBadgeProps, type StatusTone } from './StatusBadge';
export {
  StatusStrip,
  type StatusIssue,
  type StatusIssueSeverity,
  type StatusStripProps,
  type StatusStripWords,
} from './StatusStrip';
export { Tabs, type TabItem, type TabsProps } from './Tabs';
export { TickerTag, type TickerTagProps } from './TickerTag';
export {
  Timeline,
  timelineDomain,
  type TimelineDomain,
  type TimelineMarker,
  type TimelineProps,
  type TimelineRow,
  type TimelineSpan,
} from './Timeline';
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
export {
  LinkProvider,
  TextLink,
  useRenderLink,
  type LinkProviderProps,
  type LinkRenderProps,
  type LinkRenderer,
  type TextLinkProps,
} from './TextLink';
export { Tooltip, type TooltipProps, type TooltipTriggerProps } from './Tooltip';
export {
  TrackRecordChip,
  type TrackRecordChipProps,
  type TrackRecordStatus,
} from './TrackRecordChip';
export { TopBar, type TopBarProps } from './TopBar';
export { WorkspaceSwitch, type WorkspaceSwitchProps } from './WorkspaceSwitch';
