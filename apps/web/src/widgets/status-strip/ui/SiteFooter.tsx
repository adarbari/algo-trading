/**
 * The footer's late part: the data-status pill (which session's data the pages show and whether it
 * is complete). It loads with the first interaction (`SiteFooterLazy`), so no page pays its code
 * in the first load.
 */
import { DataStatusPill } from './DataStatusPill';

export interface SiteFooterProps {
  /** The viewer is an admin: the pill's detail also shows the causes the server sent. */
  admin: boolean;
}

export default function SiteFooter({ admin }: SiteFooterProps) {
  return <DataStatusPill admin={admin} />;
}
