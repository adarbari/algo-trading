/**
 * Design-system components, one folder each (components/<Name>/). Built on the primitives and
 * the final tokens (ADR 0011: tokens -> approved mockups -> components -> screens). Copy the folder
 * shape of primitives/Text (the template) and follow .claude/skills/add-ui-component.
 */
export { BarList, type BarListItem, type BarListProps } from './BarList';
export {
  DataTable,
  type ColumnWidth,
  type DataTableCellContext,
  type DataTableColumn,
  type DataTableProps,
  type DataTableSort,
} from './DataTable';
export { Disclosure, type DisclosureProps } from './Disclosure';
export {
  HeatGrid,
  type HeatGridCell,
  type HeatGridColumn,
  type HeatGridPosition,
  type HeatGridProps,
  type HeatGridRow,
  type HeatStatus,
} from './HeatGrid';
export { KeyValue, type KeyValueItem, type KeyValueProps } from './KeyValue';
export { Legend, type DataTone, type LegendItem, type LegendProps } from './Legend';
export { ShareBar, type ShareBarProps } from './ShareBar';
export { StackedBar, type StackedBarProps, type StackedBarSegment } from './StackedBar';
export { StatStrip, type StatItem, type StatStripProps } from './StatStrip';
export { Tabs, type TabItem, type TabsProps } from './Tabs';
