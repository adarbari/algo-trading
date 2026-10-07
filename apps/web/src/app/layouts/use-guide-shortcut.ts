/**
 * The Guide's shortcut: "?" opens `/guide` from anywhere, except while the focus is in a text
 * field (where "?" is a character) or a modifier key is held.
 */
import { useNavigate } from '@tanstack/react-router';
import { useEffect } from 'react';

/** Whether typing goes into the element (a text field, a select, an editable region). */
function takesText(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName);
}

export function useGuideShortcut(): void {
  const navigate = useNavigate();
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== '?' || event.ctrlKey || event.metaKey || event.altKey) return;
      if (takesText(event.target)) return;
      event.preventDefault();
      void navigate({ to: '/guide' });
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [navigate]);
}
