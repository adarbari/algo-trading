/**
 * The button that opens the Guide's search dialog (the Guide rail's search box): a full-width
 * secondary button with the search icon, so a touch user has the search without the keyboard.
 */
import { Button } from '@algotrade/ui';

import { useOpenGuideSearch } from '../model/provider';

export function GuideSearchButton() {
  const open = useOpenGuideSearch();
  return (
    <Button icon="search" fullWidth onClick={open}>
      Search the Guide
    </Button>
  );
}
