/** Entity: an instrument's option yield grid (puts and calls by delta band and expiry bucket), derived figures only, and its display rows. */
export { useOptionGrid } from './api/hooks';
export {
  bandLabel,
  columnLabel,
  columnSub,
  detailFigures,
  heatLevel,
  gridOf,
  gridUnknown,
  gridView,
  yieldText,
  type DetailFigure,
  type DisplayCell,
  type DisplayColumn,
  type DisplayRow,
  type GridExpiry,
  type GridFigures,
  type GridSide,
  type GridUnknown,
  type GridView,
  type OptionGrid,
} from './model/grid';
