/**
 * The buttons that open the app's search dialog: the Guide rail's search box (full width, with its
 * words) and the top bar's compact one (`bar`), so a touch user has the search without the
 * keyboard (⌘K does too).
 */
import { Button } from '@algotrade/ui';

import { useOpenGuideSearch } from '../model/provider';

export function GuideSearchButton({ bar = false }: { bar?: boolean }) {
  const open = useOpenGuideSearch();
  return (
    <Button icon="search" onClick={open} {...(bar ? { size: 'sm' as const } : { fullWidth: true })}>
      {bar ? 'Search' : 'Search the Guide'}
    </Button>
  );
}
