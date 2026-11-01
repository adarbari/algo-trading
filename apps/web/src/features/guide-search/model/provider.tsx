/**
 * Where the Guide's search lives: one dialog for the whole app. `GuideSearchProvider` renders it,
 * opens it on Ctrl+K / ⌘K from anywhere (text fields included: the chord is not a character) and
 * gives `useOpenGuideSearch` to whatever else opens it (the Guide rail's button). A feature
 * cannot import the router, so the app passes its navigation.
 */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';

import { GuideSearchDialog } from '../ui/GuideSearchDialog';

const OpenContext = createContext<() => void>(() => undefined);

/** Opens the search dialog. */
export function useOpenGuideSearch(): () => void {
  return useContext(OpenContext);
}

export interface GuideSearchProviderProps {
  /** Open a page of the Guide (the app's navigation). */
  navigate: (path: string) => void;
  children: ReactNode;
}

export function GuideSearchProvider({ navigate, children }: GuideSearchProviderProps) {
  const [open, setOpen] = useState(false);
  const show = useCallback(() => {
    setOpen(true);
  }, []);
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== 'k' || !(event.metaKey || event.ctrlKey) || event.altKey) {
        return;
      }
      event.preventDefault();
      setOpen((was) => !was);
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
    };
  }, []);
  return (
    <OpenContext value={show}>
      {children}
      <GuideSearchDialog open={open} onOpenChange={setOpen} onNavigate={navigate} />
    </OpenContext>
  );
}
