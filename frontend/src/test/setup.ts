import { vi } from "vitest";

import "@testing-library/jest-dom/vitest";

// jsdom doesn't implement IntersectionObserver, which motion's useInView
// (src/components/motion/InView.tsx, AnimatedGroup.tsx) relies on for
// scroll-reveal animations. A minimal inert stub is enough for component
// tests — they only need it to exist, not to actually observe anything.
class IntersectionObserverStub implements IntersectionObserver {
  readonly root: Element | Document | null = null;
  readonly rootMargin: string = "";
  readonly thresholds: ReadonlyArray<number> = [];
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }
}

vi.stubGlobal("IntersectionObserver", IntersectionObserverStub);

// jsdom doesn't implement matchMedia either, which useTilt/useMagnetic
// (reduced-motion check) and the app's own reduced-motion/dark-mode CSS
// queries rely on. Stub it to report "no match" — tests then exercise the
// full-motion code path, which is what we want to verify actually renders.
vi.stubGlobal(
  "matchMedia",
  vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
);
