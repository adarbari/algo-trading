/**
 * Feature: the Guide's search (ADR 0051): one dialog over `Query.guideSearch`, opened by Ctrl+K /
 * ⌘K from anywhere in the app (`GuideSearchProvider`, mounted once by the layout with the app's
 * navigation) or by the Guide rail's `GuideSearchButton`. The server ranks; the browser neither
 * searches nor filters (ADR 0038).
 */
export { GuideSearchButton } from './ui/GuideSearchButton';
export { GuideSearchProvider, useOpenGuideSearch } from './model/provider';
