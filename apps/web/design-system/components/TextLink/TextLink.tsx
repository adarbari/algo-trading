/**
 * TextLink: a link inside the app (a field's page, a section of this page, Explore): accent
 * text, an optional leading icon and a trailing key hint; `current` marks the page the link
 * points at. In-app paths go through the app's router link (`LinkProvider`); anchors
 * ("#reads") and URLs are plain anchors. A link to another site is an ExternalLink.
 */
import { Icon, type IconName } from '../Icon';
import { Kbd } from '../Kbd';
import { useRenderLink } from './link-context';
import styles from './TextLink.module.css';

export interface TextLinkProps {
  /** Where it goes: an in-app path ("/guide/fields/rel_volume"), an anchor ("#reads") or a URL. */
  href: string;
  /** What is there ("Relative volume"): the visible text. */
  children: string;
  /** An icon before the text (`book` for the Guide). */
  icon?: IconName;
  /** The key that opens it, shown after the text (`['?']`). */
  keys?: readonly string[];
  /** Mono face, for a catalogue name. */
  mono?: boolean;
  /** `sm` for dense lists, `base` (default), or `inherit` inside a sentence. */
  size?: 'sm' | 'base' | 'inherit';
  /** Quiet colour, for a link in a list of links (`default` is the accent). */
  tone?: 'default' | 'secondary';
  /** The page the link points at is the one shown: marks it with the accent tint. */
  current?: boolean;
}

export function TextLink({
  href,
  children,
  icon,
  keys,
  mono = false,
  size = 'base',
  tone = 'default',
  current = false,
}: TextLinkProps) {
  const render = useRenderLink();
  return render({
    href,
    className: styles.link ?? '',
    'aria-current': current ? 'page' : undefined,
    'data-active': current || undefined,
    children: (
      <span
        className={styles.content}
        data-size={size}
        data-tone={tone}
        data-mono={mono || undefined}
      >
        {icon && <Icon name={icon} size="md" />}
        {children}
        {keys && <Kbd keys={keys} size="xs" />}
      </span>
    ),
  });
}
