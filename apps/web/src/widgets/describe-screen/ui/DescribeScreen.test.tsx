import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { DescribeScreen } from './DescribeScreen';

const state = vi.hoisted((): { builder: Record<string, unknown> } => ({ builder: {} }));
const probe = vi.hoisted((): { props: Record<string, unknown> } => ({ props: {} }));

vi.mock('@/entities/feature', () => ({
  useFeatureCatalogue: () => ({ data: [{ name: 'rollup.known@v1.x' }] }),
}));
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    GuideHelp: ({ entry }: { entry: { id: string } }) => <Text>{`help ${entry.id}`}</Text>,
    termHelp: (id: string) => <Text>{`term ${id}`}</Text>,
  };
});
const dialog = vi.hoisted((): { props: Record<string, unknown> } => ({ props: {} }));
vi.mock('@/features/formula-feature', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    FormulaFeatureDialog: (props: Record<string, unknown>) => {
      dialog.props = props;
      return <Text>formula dialog</Text>;
    },
  };
});
vi.mock('@/features/screener-builder', () => ({ useScreenerBuilder: () => state.builder }));
vi.mock('@/features/screener-describe', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    hasCriteria: (d: { criteria?: Record<string, unknown> }) =>
      Object.keys(d.criteria ?? {}).length > 0,
    DescribeForm: (props: Record<string, unknown>) => {
      probe.props = props;
      return <Text>form</Text>;
    },
  };
});

const review = vi.hoisted((): { props: Record<string, unknown> } => ({ props: {} }));
vi.mock('./DraftReview', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    default: (props: Record<string, unknown>) => {
      review.props = props;
      return <Text>review</Text>;
    },
  };
});

describe('DescribeScreen', () => {
  it('hands the form the working document and the load action once the screen is ready', () => {
    const loadDocument = vi.fn();
    state.builder = { status: 'ready', id: 'mine', document: { id: 'mine' }, loadDocument };
    render(<DescribeScreen />);
    expect(screen.getByText('Describe it')).toBeInTheDocument();
    expect(probe.props['screenerId']).toBe('mine');
    expect(probe.props['document']).toEqual({ id: 'mine' });
    expect(probe.props['onDraft']).toBe(loadDocument);
  });

  it('hands the form what resets the formulas on a new answer, and the Guide help of a term', () => {
    const setFormulas = vi.fn();
    const addNotes = vi.fn();
    state.builder = {
      status: 'ready',
      id: 'mine',
      document: {},
      loadDocument: vi.fn(),
      setFormulas,
      addNotes,
    };
    render(<DescribeScreen />);
    const onAnswer = probe.props['onAnswer'] as (answer: unknown) => void;
    onAnswer({
      document: { criteria: { price: {} } },
      formulas: [{ name: 'draft_x' }],
      missing: [{ description: 'support lines' }],
    });
    expect(setFormulas).toHaveBeenCalledWith([{ name: 'draft_x' }]);
    expect(addNotes).toHaveBeenCalledWith(['support lines']);
    onAnswer({ document: {} });
    expect(setFormulas).toHaveBeenLastCalledWith([]);
    // a notes-only answer loads no draft: the screen is not dirtied (nor an uncopied preset)
    addNotes.mockClear();
    onAnswer({ document: { criteria: {} }, missing: [{ description: 'only a gap' }] });
    expect(addNotes).not.toHaveBeenCalled();
    const help = probe.props['renderTermHelp'] as (term: string) => ReactNode;
    render(<>{help('describe_failure_off')}</>);
    expect(screen.getByText('term describe_failure_off')).toBeInTheDocument();
  });

  describe('the formula under review', () => {
    const FORMULA = {
      name: 'draft_x',
      expr: 'a - b',
      unit: 'ratio',
      description: 'A minus B',
      null_meaning: 'a is missing',
    };

    it('opens the formula dialog filled in with it; saving accepts it, closing leaves it pending', () => {
      const acceptFormula = vi.fn();
      const closeReview = vi.fn();
      state.builder = {
        status: 'ready',
        id: 'mine',
        document: {},
        loadDocument: vi.fn(),
        reviewing: FORMULA,
        acceptFormula,
        closeReview,
      };
      render(<DescribeScreen />);
      expect(screen.getByText('formula dialog')).toBeInTheDocument();
      expect(dialog.props['initial']).toEqual({
        name: 'draft_x',
        expr: 'a - b',
        unit: 'ratio',
        description: 'A minus B',
        nullMeaning: 'a is missing',
      });
      (dialog.props['onSaved'] as (field: string) => void)('feature.draft_x');
      expect(acceptFormula).toHaveBeenCalledWith(FORMULA, 'feature.draft_x');
      (dialog.props['onOpenChange'] as (open: boolean) => void)(true);
      expect(closeReview).not.toHaveBeenCalled();
      (dialog.props['onOpenChange'] as (open: boolean) => void)(false);
      expect(closeReview).toHaveBeenCalled();
    });

    it('has no dialog when nothing is under review', () => {
      state.builder = {
        status: 'ready',
        id: 'mine',
        document: {},
        loadDocument: vi.fn(),
        reviewing: null,
      };
      render(<DescribeScreen />);
      expect(screen.queryByText('formula dialog')).toBeNull();
    });
  });

  it('shows the review as a lazy chunk wired to the Builder: its decisions, its criteria and its choices', async () => {
    const builder = {
      status: 'ready',
      id: 'mine',
      document: { id: 'mine' },
      loadDocument: vi.fn(),
      formulaStates: { draft_x: 'skipped' },
      reviewFormula: vi.fn(),
      skipFormula: vi.fn(),
      setCriterion: vi.fn(),
      recordChoice: vi.fn(),
      addSuggested: vi.fn(),
    };
    state.builder = builder;
    render(<DescribeScreen />);
    const renderReview = probe.props['renderReview'] as (r: unknown) => ReactNode;
    render(
      <>{renderReview({ answer: { screener_id: 'mine' }, text: 'liquid stocks', serial: 1 })}</>,
    );
    expect(await screen.findByText('review')).toBeInTheDocument();
    expect(review.props).toMatchObject({
      document: { id: 'mine' },
      formulaStates: { draft_x: 'skipped' },
      onReviewFormula: builder.reviewFormula,
      onSkipFormula: builder.skipFormula,
    });
    const pick = review.props['onPickReading'] as (c: unknown, choice: unknown) => void;
    pick({ id: 'dv' }, { event: 'choice_made', subject: 'liquid', picked: 1 });
    expect(builder.setCriterion).toHaveBeenCalledWith({ id: 'dv' });
    expect(builder.recordChoice).toHaveBeenCalledWith({
      event: 'choice_made',
      subject: 'liquid',
      picked: 1,
    });
    const accept = review.props['onAcceptSuggestion'] as (c: unknown) => void;
    accept({ field: 'f.spread', mode: 'soft' });
    expect(builder.addSuggested).toHaveBeenCalledWith({ field: 'f.spread', mode: 'soft' });
    const field = review.props['renderFieldHelp'] as (f: string) => ReactNode;
    expect(field('rollup.known@v1.x')).not.toBeNull();
    expect(field('rollup.nope@v1.y')).toBeNull();
  });

  it('a retyped part swaps the answer and loads the merged draft, keeping the other parts decisions and notes', async () => {
    const builder = {
      status: 'ready',
      id: 'mine',
      document: { id: 'mine' },
      loadDocument: vi.fn(),
      replaceFormulas: vi.fn(),
      addNotes: vi.fn(),
      removeNote: vi.fn(),
    };
    state.builder = builder;
    render(<DescribeScreen />);
    const replaceAnswer = vi.fn();
    const renderReview = probe.props['renderReview'] as (r: unknown) => ReactNode;
    render(<>{renderReview({ answer: {}, text: 's', serial: 1, replaceAnswer })}</>);
    await screen.findByText('review');
    const redrafted = review.props['onRedrafted'] as (...args: unknown[]) => void;
    const prior = {
      missing: [
        { key: 'moat', description: 'old gap' },
        { key: 'kept', description: 'unchanged gap' },
      ],
    };
    const next = {
      document: { criteria: { weekly: {} } },
      formulas: [{ name: 'draft_new' }],
      missing: [
        { key: 'kept', description: 'unchanged gap' },
        { new_key_slug: 'support', description: 'new gap' },
      ],
    };
    redrafted(next, prior, { id: 'p2', formulas: ['draft_old'] });
    expect(replaceAnswer).toHaveBeenCalledWith(next);
    expect(builder.loadDocument).toHaveBeenCalledWith(next.document);
    expect(builder.replaceFormulas).toHaveBeenCalledWith([{ name: 'draft_new' }], ['draft_old']);
    expect(builder.removeNote).toHaveBeenCalledTimes(1);
    expect(builder.removeNote).toHaveBeenCalledWith('old gap');
    expect(builder.addNotes).toHaveBeenCalledWith(['new gap']);
    // a draft with no criteria is still the draft: a retype may leave its part with none
    redrafted({ document: { criteria: {} } }, prior, { id: 'p2', formulas: [] });
    expect(builder.loadDocument).toHaveBeenLastCalledWith({ criteria: {} });
  });

  it('opens the Guide drawer only for a catalogue field', () => {
    state.builder = { status: 'ready', id: 'mine', document: {}, loadDocument: vi.fn() };
    render(<DescribeScreen />);
    const renderReview = probe.props['renderReview'] as (r: unknown) => ReactNode;
    render(<>{renderReview({ answer: {}, text: '', serial: 1 })}</>);
    return screen.findByText('review').then(() => {
      const help = review.props['renderFieldHelp'] as (field: string) => ReactNode;
      render(<>{help('rollup.known@v1.x')}</>);
      expect(screen.getByText('help rollup.known@v1.x')).toBeInTheDocument();
      expect(help('rollup.nope@v1.y')).toBeNull();
    });
  });

  it('is absent while the screen loads', () => {
    state.builder = { status: 'loading', id: 'mine', document: { id: 'mine' } };
    const { container } = render(<DescribeScreen />);
    expect(container).toBeEmptyDOMElement();
  });
});
