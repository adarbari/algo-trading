/** "On this page": the anchors of a field page's sections, in the order they appear. */
import { NavList } from '@algotrade/ui';

const SECTIONS = [
  { href: '#reads', label: 'How to read it' },
  { href: '#universe', label: 'Distribution' },
  { href: '#use', label: 'Use it for' },
  { href: '#lies', label: 'When it lies' },
  { href: '#computed', label: 'How it is computed' },
  { href: '#related', label: 'Related' },
  { href: '#ticker', label: 'On a ticker' },
  { href: '#sources', label: 'Sources' },
] as const;

export function FieldOutline() {
  return <NavList aria-label="On this page" size="sm" items={SECTIONS} />;
}
