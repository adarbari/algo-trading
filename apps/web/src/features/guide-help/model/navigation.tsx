/**
 * How "Open full page" navigates. A feature cannot import the router (routing belongs to
 * `src/app`), so the app gives it one function through `GuideHelpProvider`; without one (a test,
 * a story) it loads the address.
 */
import { createContext, useContext, type ReactNode } from 'react';

export type GuideNavigate = (path: string) => void;

const load: GuideNavigate = (path) => {
  window.location.assign(path);
};

const NavigationContext = createContext<GuideNavigate>(load);

export function GuideHelpProvider({
  navigate,
  children,
}: {
  navigate: GuideNavigate;
  children: ReactNode;
}) {
  return <NavigationContext value={navigate}>{children}</NavigationContext>;
}

export function useGuideNavigate(): GuideNavigate {
  return useContext(NavigationContext);
}
