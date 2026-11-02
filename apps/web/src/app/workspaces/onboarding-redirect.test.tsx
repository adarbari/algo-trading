import { render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { OnboardingRedirect } from './onboarding-redirect';

const hooks = vi.hoisted(() => ({ prefs: vi.fn(), navigate: vi.fn() }));
vi.mock('@/entities/appearance', () => ({ useStartTabUnanswered: hooks.prefs }));
vi.mock('@tanstack/react-router', () => ({
  Navigate: (props: unknown) => {
    hooks.navigate(props);
    return null;
  },
}));

beforeEach(() => {
  hooks.navigate.mockReset();
  window.history.pushState({}, '', '/ideas');
});

const unanswered = (value: boolean | undefined) => value;

describe('OnboardingRedirect', () => {
  it('sends a viewer with no stored start tab to the question', () => {
    hooks.prefs.mockReturnValue(unanswered(true));
    render(<OnboardingRedirect />);
    expect(hooks.navigate).toHaveBeenCalledWith({ to: '/settings', replace: true });
  });

  it('lets a viewer who answered through, and never loops on the question itself', () => {
    hooks.prefs.mockReturnValue(unanswered(false));
    render(<OnboardingRedirect />);
    hooks.prefs.mockReturnValue(unanswered(true));
    window.history.pushState({}, '', '/settings');
    render(<OnboardingRedirect />);
    expect(hooks.navigate).not.toHaveBeenCalled();
  });

  it('does nothing while the choice is unknown or when the read failed', () => {
    hooks.prefs.mockReturnValue(undefined);
    render(<OnboardingRedirect />);
    expect(hooks.navigate).not.toHaveBeenCalled();
  });
});
