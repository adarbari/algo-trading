/**
 * The Test flow's steps, numbered at the top of each page: Start, the way in taken (Guided,
 * Describe it or Expert) and the Result. A step is a link back to its page; the Result step
 * appears once a screener is named. Links go through the app's router (`LinkProvider`).
 */
import { NavTabs } from '@algotrade/ui';

import { TEST_PATHS } from './paths';

export type TestStep = 'start' | 'guided' | 'describe' | 'expert' | 'result';

export interface TestStepsProps {
  /** The step this page is. */
  at: TestStep;
  /** The screener being built or read (its Expert and Result steps link to it). */
  id?: string | undefined;
}

export function TestSteps({ at, id }: TestStepsProps) {
  const build = (() => {
    if (at === 'guided') return { href: TEST_PATHS.guided, label: 'Guided' };
    if (at === 'describe') return { href: TEST_PATHS.describe, label: 'Describe it' };
    if (at === 'start') return null;
    return {
      href: id ? TEST_PATHS.expertOf(id) : TEST_PATHS.expert,
      label: 'Expert',
    };
  })();
  const items = [
    { href: TEST_PATHS.start, label: 'Start' },
    ...(build ? [build] : []),
    ...(id && (at === 'expert' || at === 'result')
      ? [{ href: TEST_PATHS.resultOf(id), label: 'Result' }]
      : []),
  ];
  const active =
    at === 'start' ? TEST_PATHS.start : at === 'result' ? items.at(-1)?.href : build?.href;
  return (
    <NavTabs
      variant="steps"
      aria-label="Test steps"
      items={items}
      {...(active ? { activeHref: active } : {})}
    />
  );
}
