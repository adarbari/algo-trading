import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { DescribeScreen } from './DescribeScreen';

const state = vi.hoisted((): { builder: Record<string, unknown> } => ({ builder: {} }));
const probe = vi.hoisted((): { props: Record<string, unknown> } => ({ props: {} }));

vi.mock('@/features/screener-builder', () => ({ useScreenerBuilder: () => state.builder }));
vi.mock('@/features/screener-describe', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    DescribeForm: (props: Record<string, unknown>) => {
      probe.props = props;
      return <Text>form</Text>;
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

  it('is absent while the screen loads', () => {
    state.builder = { status: 'loading', id: 'mine', document: { id: 'mine' } };
    const { container } = render(<DescribeScreen />);
    expect(container).toBeEmptyDOMElement();
  });
});
