import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { Text } from '@algotrade/ui';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import {
  GuideEdgePage,
  GuideEdgesPage,
  GuideEpisodePage,
  GuideFieldPage,
  GuideFieldsPage,
  GuideGlossaryPage,
  GuideHomePage,
  GuideIndicatorPage,
  GuideMechanismPage,
  GuideScreenerCategoryPage,
  GuideScreenerPage,
  GuideScreenersPage,
  GuideRegimePage,
  GuideSituationPage,
  GuideSituationsPage,
  GuideStartIndexPage,
  GuideStartPage,
  GuideTermPage,
} from './GuidePages';

const widgets = vi.hoisted(() => ({
  rail: vi.fn(),
  fields: vi.fn(),
  field: vi.fn(),
  screener: vi.fn(),
  category: vi.fn(),
  situation: vi.fn(),
  indicator: vi.fn(),
  episode: vi.fn(),
  start: vi.fn(),
  term: vi.fn(),
  edges: vi.fn(),
  mechanism: vi.fn(),
  edge: vi.fn(),
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

vi.mock('@/widgets/guide-edges', () => ({
  GuideEdgesIndex: (props: Record<string, unknown>) => {
    widgets.edges(props);
    return <Text>edges index</Text>;
  },
}));
vi.mock('@/widgets/guide-mechanism', () => ({
  GuideMechanism: (props: Record<string, unknown>) => {
    widgets.mechanism(props);
    return <Text>mechanism page</Text>;
  },
  MechanismOutline: () => <Text>mechanism outline</Text>,
}));
vi.mock('@/widgets/guide-edge', () => ({
  GuideEdge: (props: Record<string, unknown>) => {
    widgets.edge(props);
    return <Text>edge page</Text>;
  },
  EdgeOutline: () => <Text>edge outline</Text>,
}));

vi.mock('@/widgets/guide-screeners', () => ({
  GuideScreenersIndex: () => <Text>screener index</Text>,
}));
vi.mock('@/widgets/guide-screener-category', () => ({
  GuideScreenerCategory: (props: Record<string, unknown>) => {
    widgets.category(props);
    return <Text>category page</Text>;
  },
}));
vi.mock('@/widgets/guide-screener', () => ({
  GuideScreener: (props: Record<string, unknown>) => {
    widgets.screener(props);
    return <Text>screener page</Text>;
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

vi.mock('@/widgets/guide-start', () => ({
  GuideStartIndex: () => <Text>start index</Text>,
  StartOutline: () => <Text>start outline</Text>,
  GuideStart: (props: Record<string, unknown>) => {
    widgets.start(props);
    return <Text>start page</Text>;
  },
}));
vi.mock('@/widgets/guide-glossary', () => ({
  GuideGlossaryIndex: () => <Text>glossary index</Text>,
  GuideTerm: (props: Record<string, unknown>) => {
    widgets.term(props);
    return <Text>term page</Text>;
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

  it('frames a screener family’s page with its category open in the rail', () => {
    render(<GuideScreenerCategoryPage id="breakouts" />);
    expect(screen.getByText('category page')).toBeInTheDocument();
    expect(widgets.category).toHaveBeenLastCalledWith({ id: 'breakouts' });
    expect(widgets.rail).toHaveBeenLastCalledWith({
      page: 'screener_category',
      category: 'breakouts',
    });
  });

  it('frames the screener index and a screener’s page, handing the buttons to the route', () => {
    render(<GuideScreenersPage />);
    expect(screen.getByText('screener index')).toBeInTheDocument();
    expect(widgets.rail).toHaveBeenLastCalledWith({ page: 'screeners' });
    const onSeeHits = vi.fn();
    const onOpenBuilder = vi.fn();
    render(<GuideScreenerPage id="breakout" onSeeHits={onSeeHits} onOpenBuilder={onOpenBuilder} />);
    expect(widgets.screener).toHaveBeenLastCalledWith({ id: 'breakout', onSeeHits, onOpenBuilder });
    expect(widgets.rail).toHaveBeenLastCalledWith({ page: 'screener', screener: 'breakout' });
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

  it('frames the Edges index, a mechanism’s page and an edge’s page, with the rail and the outline', () => {
    const onOpenEdgesPage = vi.fn();
    render(<GuideEdgesPage onOpenEdgesPage={onOpenEdgesPage} />);
    expect(widgets.edges).toHaveBeenLastCalledWith({ onOpenEdgesPage });
    expect(widgets.rail).toHaveBeenLastCalledWith({ page: 'edges' });
    render(<GuideMechanismPage id="slow_to_update" />);
    expect(widgets.mechanism).toHaveBeenLastCalledWith({ id: 'slow_to_update' });
    expect(widgets.rail).toHaveBeenLastCalledWith({
      page: 'mechanism',
      mechanism: 'slow_to_update',
    });
    expect(screen.getByText('mechanism outline')).toBeInTheDocument();
    const onSeeEvidence = vi.fn();
    render(<GuideEdgePage id="momentum_12_1" onSeeEvidence={onSeeEvidence} />);
    expect(widgets.edge).toHaveBeenLastCalledWith({ id: 'momentum_12_1', onSeeEvidence });
    expect(widgets.rail).toHaveBeenLastCalledWith({ page: 'edge' });
    expect(screen.getByText('edge outline')).toBeInTheDocument();
  });

  it('frames Start here and a how-to page with the rail on it', () => {
    render(<GuideStartIndexPage />);
    expect(screen.getByText('start index')).toBeInTheDocument();
    expect(widgets.rail).toHaveBeenLastCalledWith({ page: 'start' });
    render(<GuideStartPage id="read_a_result" />);
    expect(widgets.start).toHaveBeenLastCalledWith({ id: 'read_a_result' });
    expect(widgets.rail).toHaveBeenLastCalledWith({
      page: 'start_page',
      startPage: 'read_a_result',
    });
  });

  it('frames the glossary and a term’s page with the rail on the glossary', () => {
    render(<GuideGlossaryPage />);
    expect(screen.getByText('glossary index')).toBeInTheDocument();
    expect(widgets.rail).toHaveBeenLastCalledWith({ page: 'glossary' });
    render(<GuideTermPage id="not_run" />);
    expect(widgets.term).toHaveBeenLastCalledWith({ id: 'not_run' });
    expect(widgets.rail).toHaveBeenLastCalledWith({ page: 'term' });
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<GuideFieldPage name="feature.x" onAddToBuilder={vi.fn()} />);
    await expectNoA11yViolations(container);
  });
});
