import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { UnknownNote } from './UnknownNote';

const stored = {
  code: 'UNKNOWN',
  kind: 'NOT_STORED',
  guideTerm: 'unavailable_not_stored',
  kindText: 'not available for this instrument',
} as const;

describe('UnknownNote', () => {
  it('says the served kind in generic words', () => {
    render(<UnknownNote unknown={stored} />);
    expect(screen.getByText('not available for this instrument')).toBeInTheDocument();
  });

  it("says a kind in the page's own subject when it passes words, an edge is not an instrument", () => {
    render(
      <UnknownNote unknown={stored} kindWords={{ NOT_STORED: 'Not stored for this result' }} />,
    );
    expect(screen.getByText('Not stored for this result')).toBeInTheDocument();
    expect(screen.queryByText(/instrument/)).not.toBeInTheDocument();
  });

  it('keeps the kinds the page gave no words for', () => {
    render(
      <UnknownNote
        unknown={{ ...stored, kind: 'NOT_RUN', kindText: 'not run for this session' }}
        kindWords={{ NOT_STORED: 'Not stored for this result' }}
      />,
    );
    expect(screen.getByText('not run for this session')).toBeInTheDocument();
  });
});
