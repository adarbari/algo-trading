import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { ScoreMeter, type ScoreThreshold } from './ScoreMeter';

const BANDS: ScoreThreshold[] = [
  { at: 75, label: 'stress', tone: 'negative' },
  { at: 50, label: 'caution', tone: 'warning' },
];

describe('ScoreMeter', () => {
  it('is a named meter whose text names the band the value sits in', () => {
    render(<ScoreMeter value={62} label="Score" thresholds={BANDS} baseTone="positive" />);
    const meter = screen.getByRole('meter', { name: 'Score' });
    expect(meter).toHaveAttribute('aria-valuemin', '0');
    expect(meter).toHaveAttribute('aria-valuemax', '100');
    expect(meter).toHaveAttribute('aria-valuenow', '62');
    expect(meter).toHaveAttribute('aria-valuetext', '62, caution');
    expect(meter).toHaveAttribute('data-tone', 'warning');
  });

  it('takes the tone of the last band reached, and the base tone below the first', () => {
    const { rerender } = render(
      <ScoreMeter value={75} label="Score" thresholds={BANDS} baseTone="positive" />,
    );
    expect(screen.getByRole('meter')).toHaveAttribute('data-tone', 'negative');
    rerender(<ScoreMeter value={49.9} label="Score" thresholds={BANDS} baseTone="positive" />);
    expect(screen.getByRole('meter')).toHaveAttribute('data-tone', 'positive');
    expect(screen.getByRole('meter')).toHaveAttribute('aria-valuetext', '50');
  });

  it('names the band below the first threshold only when asked to', () => {
    const { rerender } = render(<ScoreMeter value={10} label="Score" thresholds={BANDS} />);
    expect(screen.getByRole('meter')).toHaveAttribute('aria-valuetext', '10');
    rerender(<ScoreMeter value={10} label="Score" thresholds={BANDS} baseLabel="calm" />);
    expect(screen.getByRole('meter')).toHaveAttribute('aria-valuetext', '10, calm');
    expect(screen.getByText('calm')).toBeInTheDocument();
  });

  it('labels each threshold and exposes the bands and caption to screen readers', () => {
    render(<ScoreMeter value={10} label="Score" thresholds={BANDS} caption="Up from 8." />);
    expect(screen.getByText('50 caution')).toBeInTheDocument();
    expect(screen.getByText('75 stress')).toBeInTheDocument();
    expect(screen.getByRole('meter')).toHaveAccessibleDescription(
      'Up from 8. Bands: caution from 50, stress from 75.',
    );
  });

  it('honours a custom scale', () => {
    render(<ScoreMeter value={5} min={0} max={10} label="Scale" />);
    expect(screen.getByRole('meter')).toHaveStyle({ '--pos': '50%' });
  });

  it('shows an unknown score as a dashed track with the reason, not a meter', () => {
    render(<ScoreMeter value={null} label="Score" unknownReason="No data for 2 Oct" />);
    expect(screen.queryByRole('meter')).toBeNull();
    expect(screen.getByRole('img')).toHaveAccessibleName('Score: unknown. No data for 2 Oct');
    expect(screen.getByText('No data for 2 Oct')).toBeInTheDocument();
  });

  it('turns the scale around for lower-is-risk: risk is at the right, bands run below the threshold', () => {
    const cushion: ScoreThreshold[] = [{ at: 200, label: 'thin', tone: 'warning' }];
    const { rerender } = render(
      <ScoreMeter
        value={120}
        min={0}
        max={600}
        label="Cushion"
        direction="lower-is-risk"
        thresholds={cushion}
        baseTone="positive"
        baseLabel="ample"
        unit="bp"
      />,
    );
    const meter = screen.getByRole('meter');
    expect(meter).toHaveAttribute('data-tone', 'warning');
    expect(meter).toHaveAttribute('aria-valuetext', '120 bp, thin');
    // 120 on 0-600 is 80% of the way toward risk; the threshold tick sits at two thirds.
    expect(meter).toHaveStyle({ '--pos': '80%' });
    expect(screen.getByText('200 bp thin')).toBeInTheDocument();
    expect(meter).toHaveAccessibleDescription('Bands: thin at or below 200 bp.');
    rerender(
      <ScoreMeter
        value={200}
        min={0}
        max={600}
        label="Cushion"
        direction="lower-is-risk"
        thresholds={cushion}
        baseTone="positive"
        baseLabel="ample"
      />,
    );
    expect(screen.getByRole('meter')).toHaveAttribute('aria-valuetext', '200, thin');
    rerender(
      <ScoreMeter
        value={201}
        min={0}
        max={600}
        label="Cushion"
        direction="lower-is-risk"
        thresholds={cushion}
        baseTone="positive"
        baseLabel="ample"
      />,
    );
    expect(screen.getByRole('meter')).toHaveAttribute('data-tone', 'positive');
    expect(screen.getByRole('meter')).toHaveAttribute('aria-valuetext', '201, ample');
  });

  it('says so when the value is off the scale and pins the marker to the nearer end', () => {
    const { rerender } = render(<ScoreMeter value={130} label="Score" thresholds={BANDS} />);
    const meter = screen.getByRole('meter');
    expect(meter).toHaveStyle({ '--pos': '100%' });
    expect(meter).toHaveAttribute('aria-valuenow', '100');
    expect(meter).toHaveAttribute('aria-valuetext', '130, stress, above range');
    expect(screen.getByText('above range')).toBeInTheDocument();
    rerender(<ScoreMeter value={-3} label="Score" thresholds={BANDS} />);
    expect(screen.getByRole('meter')).toHaveStyle({ '--pos': '0%' });
    expect(screen.getByRole('meter')).toHaveAttribute('aria-valuetext', '−3, below range');
    expect(screen.getByText('below range')).toBeInTheDocument();
  });

  it('announces loading', () => {
    render(<ScoreMeter value={1} label="Score" loading />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading Score');
  });

  it('has no accessibility violations', async () => {
    const { container, rerender } = render(
      <ScoreMeter value={62} label="Score" thresholds={BANDS} caption="Caption" />,
    );
    await expectNoA11yViolations(container);
    rerender(<ScoreMeter value={null} label="Score" />);
    await expectNoA11yViolations(container);
  });
});
