/**
 * The button that opens the app's search dialog (⌘K does too): the Guide rail's search box and the
 * account menu's first item, full width with the search icon, so a touch user has the search
 * without the keyboard and the phone's top bar keeps its room.
 */
import { Button } from '@algotrade/ui';

import { useOpenGuideSearch } from '../model/provider';

export function GuideSearchButton({ label = 'Search the Guide' }: { label?: string }) {
  const open = useOpenGuideSearch();
  return (
    <Button icon="search" fullWidth onClick={open}>
      {label}
    </Button>
  );
}
