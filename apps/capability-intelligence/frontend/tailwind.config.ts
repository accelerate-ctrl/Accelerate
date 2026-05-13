import type { Config } from 'tailwindcss';

// Zennify Design System v2.4.14 — canonical palette extracted from the
// official `Zennify_Presentation_Template_2026.pptx` (57-color system).
// Source of truth: zds-v2/references/01_palette/color_system.md.
//
// Names use `zen-*` for compatibility with existing components, plus
// semantic aliases (text/bg/surface/...) for new code.
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        zen: {
          // Greens — primary brand family
          'dark-green': '#1C4A4D',     // body text on light bg
          'dark-teal': '#185F60',      // dark card fills, primary dark
          teal: '#27BBAF',             // headlines on light, accent bars
          'accent-green': '#139F94',   // icon fills, secondary accent
          'light-teal': '#62D7B8',     // building level, highlights
          mint: '#79E2BF',             // highlights on dark, decorative
          'light-green': '#B0EDD3',    // text on dark, solution labels
          ice: '#E8F7F6',              // card tint, subtle bg
          'white-green': '#E8F7F6',    // alias for legacy components

          // Blues & purples — secondary family
          lavender: '#F2F4F9',         // primary card fill
          'light-blue': '#A5C6FF',     // sparse accent
          blue: '#3D81F6',             // benchmark medians
          'purple-grey': '#C7D3EC',    // sidebar panels, tertiary bg
          purple: '#B19CD8',
          'dark-purple': '#8094C0',    // muted accent
          'deep-purple': '#735BA1',

          // Oranges — accent family
          'light-orange': '#FFCB99',   // activating level, stat card bg
          orange: '#FE9732',           // stronger emphasis

          // Functional
          white: '#FFFFFF',
          'light-bg': '#F5F5F5',
          'warm-white': '#F7F6F5',
          'separator': '#E5E7EB',
          'muted-text': '#6B7280',
          'text-gray': '#4A5568',
          navy: '#001E48',

          // DMA maturity bands
          activating: '#FFCB99',
          building: '#62D7B8',
          competing: '#27BBAF',
          differentiating: '#139F94',
          'above-bench': '#059669',
          'below-bench': '#C25008',
        },
        tier: {
          t1: '#185F60',
          t2: '#27BBAF',
          t3: '#62D7B8',
          t4: '#FFCB99',
          t5: '#FE9732',
        },
        claim: {
          fact: '#1C4A4D',
          inference: '#27BBAF',
          hypothesis: '#FFCB99',
          ceiling: '#FE9732',
        },
        cluster: {
          'vcc-01': '#1C4A4D',
          'vcc-02': '#185F60',
          'vcc-03': '#27BBAF',
          'vcc-04': '#62D7B8',
          'vcc-05': '#B0EDD3',
          'vcc-06': '#FFCB99',
          'vcc-07': '#FE9732',
          'vcc-08': '#E8F7F6',
        },
      },
      fontFamily: {
        // DM Sans is the canonical brand font per ZDS v2.
        sans: ['DM Sans', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      borderRadius: { DEFAULT: '8px', md: '8px', lg: '12px' },
      transitionDuration: { DEFAULT: '200ms', drawer: '300ms' },
    },
  },
  plugins: [],
} satisfies Config;
