import type { Config } from 'tailwindcss';

// Zennify brand tokens — locked per spec §14.
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // 8 Zennify brand tokens
        zen: {
          'dark-green': '#1c4a4d',
          'dark-teal': '#185f60',
          teal: '#27bbaf',
          'light-teal': '#62d7b8',
          'light-green': '#b0eed3',
          'white-green': '#e8f7f6',
          'light-orange': '#ffcb99',
          orange: '#fe9732',
        },
        // Source-tier chips
        tier: {
          t1: '#185f60',
          t2: '#27bbaf',
          t3: '#62d7b8',
          t4: '#ffcb99',
          t5: '#fe9732',
        },
        // Claim-label badges
        claim: {
          fact: '#1c4a4d',
          inference: '#27bbaf',
          hypothesis: '#ffcb99',
          ceiling: '#fe9732',
        },
        // Value-chain clusters (8). Subject to refinement in Batch 2.
        cluster: {
          'vcc-01': '#1c4a4d',
          'vcc-02': '#185f60',
          'vcc-03': '#27bbaf',
          'vcc-04': '#62d7b8',
          'vcc-05': '#b0eed3',
          'vcc-06': '#ffcb99',
          'vcc-07': '#fe9732',
          'vcc-08': '#e8f7f6',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      borderRadius: { DEFAULT: '8px', md: '8px', lg: '12px' },
      transitionDuration: { DEFAULT: '200ms', drawer: '300ms' },
    },
  },
  plugins: [],
} satisfies Config;
