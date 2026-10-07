import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { Text } from '@algotrade/ui';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import { GuideFieldPage, GuideFieldsPage, GuideHomePage } from './GuidePages';

const widgets = vi.hoisted(() => ({ rail: vi.fn(), fields: vi.fn(), field: vi.fn() }));

vi.mock('@/widgets/guide-rail', () => ({
  GuideRail: (props: Record<string, unknown>) => {
    widgets.rail(props);
    return <Text>rail</Text>;
  },
}));
vi.mock('@/widgets/guide-home', () => ({ GuideHome: () => <Text>home</Text> }));
vi.mock('@/widgets/guide-fields', () => ({
  GuideFieldsIndex: (props: Record<string, unknown>) => {
    widgets.fields(props);
    return <Text>field index</Text>;
  },
}));
vi.mock('@/widgets/guide-field', () => ({
  GuideField: (props: Record<string, unknown>) => {
    widgets.field(props);
    return <Text>field page</Text>;
  },
  FieldOutline: () => <Text>outline</Text>,
}));

describe('Guide pages', () => {
  it('frames the home with the rail', () => {
    render(<GuideHomePage />);
    expect(screen.getByText('home')).toBeInTheDocument();
    expect(widgets.rail).toHaveBeenLastCalledWith({ page: 'home' });
  });

  it('hands the field index its view, theme and intent, and opens the theme in the rail', () => {
    const onViewChange = vi.fn();
    render(<GuideFieldsPage view="intent" theme="volume" intent="x" onViewChange={onViewChange} />);
    expect(widgets.fields).toHaveBeenLastCalledWith({
      view: 'intent',
      theme: 'volume',
      intent: 'x',
      onViewChange,
    });
    expect(widgets.rail).toHaveBeenLastCalledWith({ page: 'fields', theme: 'volume' });
  });

  it('frames a field page with the rail on that field and the "On this page" list', () => {
    const onAddToBuilder = vi.fn();
    render(<GuideFieldPage name="feature.x" onAddToBuilder={onAddToBuilder} />);
    expect(widgets.field).toHaveBeenLastCalledWith({ name: 'feature.x', onAddToBuilder });
    expect(widgets.rail).toHaveBeenLastCalledWith({ page: 'field', field: 'feature.x' });
    expect(screen.getByText('outline')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<GuideFieldPage name="feature.x" onAddToBuilder={vi.fn()} />);
    await expectNoA11yViolations(container);
  });
});
