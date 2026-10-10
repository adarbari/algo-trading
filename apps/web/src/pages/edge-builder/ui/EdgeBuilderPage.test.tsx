import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { EdgeBuilderPage } from './EdgeBuilderPage';

interface Runner {
  running: boolean;
  error: Error | null;
  run: { state: string } | undefined;
}
const state = vi.hoisted((): { start: ReturnType<typeof vi.fn>; runner: Runner } => ({
  start: vi.fn(),
  runner: { running: true, error: null, run: { state: 'running' } },
}));

vi.mock('@/features/edge-builder', async () => {
  const { Button, Text } = await import('@algotrade/ui');
  return {
    HelpProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    EdgeBuilder: (props: {
      id: string | null;
      addScreen?: string;
      onSaved: (id: string, run: boolean) => void;
      onOpenScreen: (id: string | null) => void;
    }) => (
      <>
        <Text>{`builder ${props.id ?? 'new'} ${props.addScreen ?? ''}`}</Text>
        <Button
          onClick={() => {
            props.onSaved('mine', false);
          }}
        >
          save
        </Button>
        <Button
          onClick={() => {
            props.onSaved('mine', true);
          }}
        >
          save and run
        </Button>
        <Button
          onClick={() => {
            props.onOpenScreen('momo');
          }}
        >
          edit screen
        </Button>
      </>
    ),
  };
});
vi.mock('@/features/edge-evaluation', () => ({
  useRunEvaluation: () => ({ start: state.start, ...state.runner }),
  evaluationMessage: () => 'Evaluating…',
}));
vi.mock('@/features/guide-help', () => ({ GuideHelp: () => null }));

beforeEach(() => {
  state.start.mockClear();
  state.runner = { running: true, error: null, run: { state: 'running' } };
});

function setup(id: string | null = 'mine') {
  const props = {
    onOpenScreen: vi.fn(),
    onCancel: vi.fn(),
    onOpenEdge: vi.fn(),
  };
  render(<EdgeBuilderPage id={id} addScreen="momo" {...props} />);
  return props;
}

describe('EdgeBuilderPage', () => {
  it('shows the builder, passing the screen to add, and tells which edge opens the Screen Builder', async () => {
    const { onOpenScreen } = setup('mine');
    expect(screen.getByText('builder mine momo')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'edit screen' }));
    expect(onOpenScreen).toHaveBeenCalledWith('momo', 'mine');
  });

  it('a new edge opens the Screen Builder with no edge id', async () => {
    const { onOpenScreen } = setup(null);
    await userEvent.click(screen.getByRole('button', { name: 'edit screen' }));
    expect(onOpenScreen).toHaveBeenCalledWith('momo', null);
  });

  it('opens the edge after a save without a run', async () => {
    const { onOpenEdge } = setup();
    await userEvent.click(screen.getByRole('button', { name: 'save' }));
    expect(onOpenEdge).toHaveBeenCalledWith('mine');
    expect(state.start).not.toHaveBeenCalled();
  });

  it('runs the backtest once after "Save and run backtest" and shows it running', async () => {
    const { onOpenEdge } = setup();
    await userEvent.click(screen.getByRole('button', { name: 'save and run' }));
    expect(screen.getByText('Backtest running')).toBeInTheDocument();
    expect(screen.getByText('Evaluating…')).toBeInTheDocument();
    expect(state.start).toHaveBeenCalledOnce();
    expect(state.start).toHaveBeenCalledWith(false);
    await userEvent.click(screen.getByRole('button', { name: 'Open the edge' }));
    expect(onOpenEdge).toHaveBeenCalledWith('mine');
  });

  it('offers the result when the backtest finished', async () => {
    state.runner = { running: false, error: null, run: { state: 'complete' } };
    setup();
    await userEvent.click(screen.getByRole('button', { name: 'save and run' }));
    expect(screen.getByText('Backtest finished')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Show result' })).toBeInTheDocument();
  });

  it('shows the refusal when the backtest did not start', async () => {
    state.runner = {
      running: false,
      error: new Error('another evaluation is running'),
      run: undefined,
    };
    setup();
    await userEvent.click(screen.getByRole('button', { name: 'save and run' }));
    expect(screen.getByText('The backtest did not start')).toBeInTheDocument();
  });
});
