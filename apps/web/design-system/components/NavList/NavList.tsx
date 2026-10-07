/**
 * NavList: a compact vertical list of links, optionally nested one level (a section and its
 * themes, a theme and its fields), each with an optional count; the current one carries
 * `aria-current="page"` and the accent tint. Used as the Guide's side rail and, with anchors,
 * as a page's "On this page" list. Links go through the app's router link (`LinkProvider`).
 */
import { useRenderLink } from '../TextLink';
import styles from './NavList.module.css';

export interface NavListItem {
  /** An in-app path, an anchor ("#reads") or a URL. */
  href: string;
  label: string;
  /** A count shown at the end of the row (how many entries are behind it). */
  count?: number;
  /** Mono face, for a catalogue name. */
  mono?: boolean;
  /** This is the page shown. */
  current?: boolean;
  /** Links nested under this one (shown always; the app decides what to include). */
  children?: readonly NavListItem[];
}

export interface NavListProps {
  /** The navigation landmark's name ("Guide", "On this page"). */
  'aria-label': string;
  items: readonly NavListItem[];
  /** `sm` for a page's own anchors; `base` (default) for a rail. */
  size?: 'sm' | 'base';
}

function Items({
  items,
  level,
  size,
}: {
  items: readonly NavListItem[];
  level: number;
  size: 'sm' | 'base';
}) {
  const render = useRenderLink();
  return (
    <ul className={styles.list} data-level={level}>
      {items.map((item) => (
        <li key={item.href} className={styles.item}>
          {render({
            href: item.href,
            className: styles.link ?? '',
            'aria-current': item.current ? 'page' : undefined,
            'data-active': item.current || undefined,
            children: (
              <>
                <span className={styles.label} data-mono={item.mono || undefined} data-size={size}>
                  {item.label}
                </span>
                {item.count !== undefined && (
                  <span className={styles.count}>{item.count.toLocaleString('en-US')}</span>
                )}
              </>
            ),
          })}
          {item.children && item.children.length > 0 && (
            <Items items={item.children} level={level + 1} size={size} />
          )}
        </li>
      ))}
    </ul>
  );
}

export function NavList({ 'aria-label': ariaLabel, items, size = 'base' }: NavListProps) {
  return (
    <nav aria-label={ariaLabel} className={styles.nav}>
      <Items items={items} level={0} size={size} />
    </nav>
  );
}
