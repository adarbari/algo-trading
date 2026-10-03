/** The typed design tokens (FINAL: approved mockups 2026-10-03, ADR 0011): the single source of tokens.css. */
export {
  colorRoles,
  dark,
  light,
  SERIES,
  STATUSES,
  textPairs,
  type Palette,
  type Series,
  type Status,
  type StatusColor,
} from './color';
export { AA_GRAPHIC, AA_TEXT, contrastRatio, luminance } from './contrast';
export { defaultDensity, density, type Density, type DensityName } from './density';
export { zIndex } from './layers';
export { duration, easing } from './motion';
export { borderWidth, focusRing, radius, type Radius } from './shape';
export { breakpoint, size, space, spaceName, type Breakpoint, type Space } from './space';
export {
  fontFamily,
  fontFeatures,
  fontSize,
  fontWeight,
  type FontSize,
  type FontWeight,
} from './typography';
