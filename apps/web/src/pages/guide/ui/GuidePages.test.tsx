import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { Text } from '@algotrade/ui';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import {
  GuideEpisodePage,
  GuideFieldPage,
  GuideFieldsPage,
  GuideHomePage,
  GuideIndicatorPage,
  GuidePlaybookPage,
  GuidePlaybooksPage,
  GuideRegimePage,
  GuideSituationPage,
  GuideSituationsPage,
} from './GuidePages';

const widgets = vi.hoisted(() => ({
  rail: vi.fn(),
  fields: vi.fn(),
  field: vi.fn(),
  playbook: vi.fn(),
  situation: vi.fn(),
  indicator: vi.fn(),
  episode: vi.fn(),
}));

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

vi.mock('@/widgets/guide-playbooks', () => ({
  GuidePlaybooksIndex: () => <Text>playbook index</Text>,
}));
vi.mock('@/widgets/guide-playbook', () => ({
  GuidePlaybook: (props: Record<string, unknown>) => {
    widgets.playbook(props);
    return <Text>playbook page</Text>;
  },
}));
vi.mock('@/widgets/guide-regime', () => ({
  GuideRegimeIndex: () => <Text>regime index</Text>,
  GuideIndicator: (props: Record<string, unknown>) => {
    widgets.indicator(props);
    return <Text>indicator page</Text>;
  },
  GuideEpisode: (props: Record<string, unknown>) => {
    widgets.episode(props);
    return <Text>episode page</Text>;
  },
}));
vi.mock('@/widgets/guide-situations', () => ({
  GuideSituationsIndex: () => <Text>situation index</Text>,
  GuideSituation: (props: Record<string, unknown>) => {
    widgets.situation(props);
    return <Text>situation page</Text>;
  },
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

  it('frames the playbook index and a playbook’s page, handing the buttons to the route', () => {
    render(<GuidePlaybooksPage />);
    expect(screen.getByText('playbook index')).toBeInTheDocument();
    expect(widgets.rail).toHaveBeenLastCalledWith({ page: 'playbooks' });
    const onSeeHits = vi.fn();
    const onOpenBuilder = vi.fn();
    render(<GuidePlaybookPage id="breakout" onSeeHits={onSeeHits} onOpenBuilder={onOpenBuilder} />);
    expect(widgets.playbook).toHaveBeenLastCalledWith({ id: 'breakout', onSeeHits, onOpenBuilder });
    expect(widgets.rail).toHaveBeenLastCalledWith({ page: 'playbook', playbook: 'breakout' });
  });

  it('frames the situation index and a situation’s page with the rail on it', () => {
    render(<GuideSituationsPage />);
    expect(screen.getByText('situation index')).toBeInTheDocument();
    expect(widgets.rail).toHaveBeenLastCalledWith({ page: 'situations' });
    render(<GuideSituationPage slug="earnings-gap" />);
    expect(widgets.situation).toHaveBeenLastCalledWith({ slug: 'earnings-gap' });
    expect(widgets.rail).toHaveBeenLastCalledWith({ page: 'situation', situation: 'earnings-gap' });
  });

  it('frames the regime index, an indicator’s page and a market fall’s page with the rail on it', () => {
    render(<GuideRegimePage />);
    expect(screen.getByText('regime index')).toBeInTheDocument();
    expect(widgets.rail).toHaveBeenLastCalledWith({ page: 'regime' });
    render(<GuideIndicatorPage indicatorKey="curve_10y3m" />);
    expect(widgets.indicator).toHaveBeenLastCalledWith({ indicatorKey: 'curve_10y3m' });
    expect(widgets.rail).toHaveBeenLastCalledWith({ page: 'indicator', indicator: 'curve_10y3m' });
    render(<GuideEpisodePage slug="gfc_2007" />);
    expect(widgets.episode).toHaveBeenLastCalledWith({ slug: 'gfc_2007' });
    expect(widgets.rail).toHaveBeenLastCalledWith({ page: 'episode', episode: 'gfc_2007' });
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<GuideFieldPage name="feature.x" onAddToBuilder={vi.fn()} />);
    await expectNoA11yViolations(container);
  });
});
