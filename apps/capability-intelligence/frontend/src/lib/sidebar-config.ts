// Single source of truth for the 9 sidebar groups + 28 page entries (per spec §13).
// Each entry maps to a route in routes.tsx and a page file in src/pages/.

export type NavEntry = {
  label: string;
  path: string;
  batch: number;
};

export type NavGroup = {
  label: string;
  entries: NavEntry[];
};

export const navigation: NavGroup[] = [
  {
    label: 'Explore',
    entries: [
      { label: 'Mission Control', path: '/', batch: 1 },
      { label: 'Capability Explorer', path: '/explorer', batch: 1 },
      { label: 'Subcap Deep Dive', path: '/subcap', batch: 1 },
      { label: 'Value Chain Atlas', path: '/value-chain', batch: 2 },
      { label: 'Subvertical Compare', path: '/subvertical-compare', batch: 2 },
    ],
  },
  {
    label: 'Catalogue Tools',
    entries: [
      { label: 'Platform Catalog', path: '/platforms', batch: 2 },
      { label: 'Use Case Explorer', path: '/use-cases', batch: 2 },
      { label: 'Maturity Heatmap', path: '/maturity', batch: 2 },
      { label: 'Knowledge Graph', path: '/graph', batch: 2 },
    ],
  },
  {
    label: 'Project Validation',
    entries: [
      { label: 'SOW Library', path: '/sows', batch: 3 },
      { label: 'Story Library', path: '/stories', batch: 3 },
      { label: 'Project–Subcap Trace', path: '/trace', batch: 3 },
    ],
  },
  {
    label: 'Public Intelligence',
    entries: [
      { label: 'News Watch', path: '/news', batch: 4 },
      { label: 'Trends Monitor', path: '/trends', batch: 4 },
      { label: 'AI Suggestions', path: '/suggestions', batch: 4 },
      { label: 'Benchmarks Studio', path: '/benchmarks', batch: 5 },
    ],
  },
  {
    label: 'Strategic Synthesis',
    entries: [{ label: 'Quarterly Strategic Digest', path: '/digest', batch: 7 }],
  },
  {
    label: 'Lifecycle & Competition',
    entries: [
      { label: 'Lifecycle Manager', path: '/lifecycle', batch: 6 },
      { label: 'Vendor Intelligence', path: '/vendors', batch: 6 },
      { label: 'Client Journey Atlas', path: '/clients', batch: 6 },
    ],
  },
  {
    label: 'Versioning & QA',
    entries: [
      { label: 'Version Timeline', path: '/versions', batch: 1 },
      { label: 'Diff Viewer', path: '/diff', batch: 1 },
      { label: 'Change Flags Inbox', path: '/flags', batch: 1 },
      { label: 'Validation Gates Log', path: '/validation-gates', batch: 4 },
      { label: 'QA & Audit Dashboard', path: '/audit', batch: 8 },
    ],
  },
  {
    label: 'Reasoning & RAG',
    entries: [
      { label: 'Reasoning Chain Viewer', path: '/reasoning', batch: 4 },
      { label: 'AI Chat', path: '/chat', batch: 8 },
    ],
  },
  {
    label: 'Sandbox & Personas',
    entries: [{ label: 'What-If Simulator', path: '/what-if', batch: 8 }],
  },
];

export const flatEntries: NavEntry[] = navigation.flatMap((g) => g.entries);
