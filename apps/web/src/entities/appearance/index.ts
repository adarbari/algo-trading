/**
 * Entity: the user's appearance (ADR 0085): `useTheme` is the stored Light / Dark / System choice
 * to apply, `useSaveTheme` changes it (read through GraphQL, written through REST, with a copy on
 * this device so the page paints in the right theme before the first response).
 */
export { useSaveTheme, useStartTabUnanswered, useTheme } from './api/appearance';
export { THEMES, THEME_KEY, readDeviceTheme, type ThemeChoice } from './model/theme';
