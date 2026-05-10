// Typed API client. Real auth wired in Batch 1; user is the dev-mode email
// for now and switches to Firebase ID token in production (Batch 9).

const DEV_TOKEN = 'dev-dev@zennify.com';

function url(path: string): string {
  return `/api${path}`;
}

function headers(extra?: HeadersInit): HeadersInit {
  return {
    Authorization: `Bearer ${DEV_TOKEN}`,
    'Content-Type': 'application/json',
    ...(extra || {}),
  };
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(url(path), { headers: headers() });
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
  return (await res.json()) as T;
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(url(path), {
    method: 'POST',
    headers: headers(),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} → ${res.status}`);
  return (await res.json()) as T;
}

// ─── Types ──────────────────────────────────────────────────────────────────

export type Pillar = {
  pillar_id: string;
  name: string;
  schema_status: 'complete' | 'incomplete' | 'missing';
  source_file_id?: string;
  source_file_name?: string;
  source_file_modified_at?: string;
  source_version?: string;
};

export type Subcap = {
  sub_cap_id: string;
  sub_cap_name: string;
  pillar_id: string;
  category_id: string;
  l1_capability: string;
  description?: string;
  solution_type?: string;
  tier?: string;
  personas?: string[];
  l3_platforms?: string[];
  l4_features?: string[];
  use_cases?: string[];
  story_refs?: string[];
  zennify_status?: string;
  lifecycle_state?: string;
};

export type SubcapDetail = {
  subcap: Subcap;
  maturity: Record<string, unknown> | null;
  l4_features: Record<string, unknown>[];
  use_cases: Record<string, unknown>[];
  themes: Record<string, unknown>[];
  stories: Record<string, unknown>[];
};

export type Tree = {
  pillars: Array<{
    pillar_id: string;
    name: string;
    categories: Array<{
      category_id: string;
      name: string;
      l1: Array<{ name: string; subcaps: Array<{ sub_cap_id: string; sub_cap_name: string; tier?: string; lifecycle_state?: string }> }>;
    }>;
  }>;
};

export type Overview = {
  pillars: Record<string, { pillar: Pillar; category_count: number; subcap_count: number; active_subcaps: number }>;
  totals: { pillars_loaded: number; subcaps: number; open_flags: number };
  last_ingest: { run_id: string; started_at: string; completed_at: string; pillars_loaded: string[] } | null;
};

export type DiscoveredFile = {
  pillar_id: string;
  file_id: string;
  file_name: string;
  modified_at: string;
  parsed_version?: string;
  is_google_sheet: boolean;
  source: 'drive' | 'local';
};

export type IngestRun = {
  run_id: string;
  started_at: string;
  completed_at: string;
  pillars_attempted: string[];
  pillars_loaded: string[];
  pillars_skipped: Array<{ pillar_id: string; reason: string }>;
  counts_by_pillar: Record<string, Record<string, number>>;
  flags_raised: string[];
};

export type CatalogueVersion = {
  version_id: string;
  label?: string;
  summary?: string;
  created_at: string;
  created_by: string;
  pillar_counts: Record<string, number>;
  is_current: boolean;
  source_files: Record<string, { file_name?: string; version?: string }>;
};

export type Diff = {
  version_a: string;
  version_b: string;
  added_subcaps: string[];
  removed_subcaps: string[];
  modified_subcaps: Array<{ sub_cap_id: string; fields: Record<string, { a: unknown; b: unknown }> }>;
  added_categories: string[];
  removed_categories: string[];
  pillar_count_deltas: Record<string, number>;
};

// ─── Batch 8 ────────────────────────────────────────────────────────────────

export type ChatTurn = {
  role: 'user' | 'assistant' | 'system';
  text: string;
  citations?: string[];
  chain_id?: string | null;
  cost_usd?: number;
  sources?: Array<{ id: string; kind?: string; title?: string; text?: string; url?: string | null }>;
  created_at?: string;
};

export type ChatReply = {
  conversation_id: string;
  message_id: string;
  reply: string;
  citations: string[];
  chain_id?: string | null;
  cost_usd: number;
  sources: Array<{ id: string; kind?: string; title?: string; text?: string; url?: string | null }>;
};

export type ChatConversation = {
  conversation_id: string;
  created_at: string;
  updated_at: string;
  turns: ChatTurn[];
};

export type WhatIfStateChange = {
  sub_cap_id: string;
  sub_cap_name: string;
  before: { state: string | null; score: number | null };
  after: { state: string; score: number };
};

export type WhatIfAdoptionChange = {
  vendor_id: string;
  cohort_id: string;
  before_pct: number;
  after_pct: number;
};

export type WhatIfSimulation = {
  actions_applied: number;
  state_changes: WhatIfStateChange[];
  adoption_changes: WhatIfAdoptionChange[];
  new_transitions: Array<{
    sub_cap_id: string;
    from_state: string;
    to_state: string;
    score: number;
    transitioned_at: string;
  }>;
  summary: string;
  computed_at: string;
};

export type Notification = {
  id: string;
  kind: string;
  severity: 'critical' | 'warn' | 'info';
  title: string;
  detail: string;
  ref_collection?: string | null;
  ref_id?: string | null;
  created_at: string;
  read: boolean;
};

export type EvalRun = {
  run_id: string;
  dataset_id: string;
  kind: string;
  started_at: string;
  completed_at: string;
  n_cases: number;
  n_passed: number;
  pass_rate: number;
  mean_score: number;
  cases: Array<{ case_id: string; passed: boolean; score: number; notes?: string | null }>;
};

// ─── Batch 7 ────────────────────────────────────────────────────────────────

export type DigestPriority = {
  sub_cap_id: string;
  sub_cap_name: string;
  state?: string | null;
  score?: number | null;
  confidence?: number | null;
  narrative: string;
  recommendation: string;
  evidence_sows: Array<{
    sow_id?: string;
    client?: string;
    status?: string;
    excerpt?: string;
    method?: string;
    confidence?: number;
  }>;
  evidence_benchmarks: Array<{
    metric_id?: string;
    cohort_id?: string;
    period?: string;
    verdict?: string;
    n?: number;
    p25?: number;
    p50?: number;
    p75?: number;
  }>;
  evidence_news: Array<{
    id?: string;
    title?: string;
    source?: string;
    published_at?: string;
    url?: string | null;
    kind?: string;
  }>;
  delta?: {
    previous_state?: string | null;
    previous_score?: number | null;
    previous_period?: string;
  } | null;
  chain_id?: string | null;
  cost_usd: number;
};

export type StrategicDigest = {
  digest_id: string;
  subvertical: string;
  period: string;
  previous_period: string | null;
  generated_at: string;
  model: string;
  priorities: DigestPriority[];
  summary: string;
  sources_count: number;
  total_cost_usd: number;
};

export type AuditFinding = {
  kind: string;
  severity: 'critical' | 'warn' | 'info';
  title: string;
  detail: string;
  ref_collection?: string | null;
  ref_id?: string | null;
  metadata?: Record<string, unknown>;
};

export type AuditReport = {
  report_id: string;
  started_at: string;
  completed_at: string;
  findings: AuditFinding[];
  summary: { critical: number; warn: number; info: number };
  inputs_seen: Record<string, number>;
};

// ─── Batch 6 ────────────────────────────────────────────────────────────────

export type LifecycleState =
  | 'EMERGING' | 'RISING' | 'STABLE' | 'DECLINING' | 'FADING' | 'DEAD';

export type LifecycleScore = {
  sub_cap_id: string;
  sub_cap_name: string;
  state: LifecycleState;
  score: number;
  confidence: number;
  signals: {
    sow_active: number;
    sow_prospect: number;
    sow_inactive: number;
    sow_archived: number;
    sow_recency_days: number | null;
    canonical_stories: number;
    jira_stories: number;
    news_last_90d: number;
    news_recency_days: number | null;
    trends_last_90d: number;
    benchmark_indicative: number;
    benchmark_full: number;
    benchmark_exploratory: number;
    ai_extrapolations: number;
  };
  last_signal_at?: string | null;
  computed_at: string;
};

export type LifecycleTransition = {
  id: string;
  sub_cap_id: string;
  from_state: LifecycleState;
  to_state: LifecycleState;
  score: number;
  transitioned_at: string;
};

export type LifecycleRunSummary = {
  run_id: string;
  started_at: string;
  completed_at: string;
  subcaps_scored: number;
  state_distribution: Record<LifecycleState, number>;
  transitions: number;
  inputs_seen: Record<string, number>;
};

export type VendorProfile = {
  vendor_id: string;
  name: string;
  category?: string | null;
  companies: string[];
  cohorts: string[];
  news_mentions: number;
  avg_confidence: number;
  last_seen_at?: string | null;
  ai_signal_avg?: number | null;
};

export type CohortAdoption = {
  id: string;
  vendor_id: string;
  cohort_id: string;
  adopters: string[];
  cohort_size: number;
  adoption_pct: number;
  avg_confidence: number;
};

export type VendorEvent = {
  id: string;
  vendor_id: string;
  vendor_name: string;
  kind: string;
  title?: string;
  text?: string;
  url?: string | null;
  source?: string;
  published_at?: string;
};

export type VendorHeatmap = {
  vendors: string[];
  cohorts: string[];
  cells: Array<{
    vendor_id: string;
    cohort_id: string;
    adoption_pct: number;
    adopters: string[];
    cohort_size: number;
  }>;
};

export type ClientJourney = {
  client_name: string;
  sow_count_active: number;
  sow_count_prospect: number;
  sow_count_inactive: number;
  sow_count_archived: number;
  cohorts: string[];
  subverticals: string[];
  asset_size_usd_bn: number | null;
  touched_subcaps: Array<{
    sub_cap_id: string;
    sub_cap_name: string;
    state?: LifecycleState | null;
    score?: number | null;
    confidence?: number | null;
    sow_count: number;
    sow_excerpts: string[];
    canonical_story_count: number;
    jira_story_count: number;
  }>;
  vendor_stack: Array<{
    vendor: string;
    category?: string | null;
    confidence: number;
    cohort_adoption: Array<{ cohort_id: string; adoption_pct: number }>;
  }>;
  state_distribution: Record<string, number>;
  most_recent_signal_at?: string | null;
  computed_at: string;
};

export type DmaPacket = {
  schema_version: string;
  generated_at: string;
  client: string;
  asset_size_usd_bn: number | null;
  subverticals: string[];
  cohorts: string[];
  engagement: { active: number; prospect: number; inactive: number; archived: number };
  vendor_stack: Array<{ vendor: string; category?: string | null; confidence: number }>;
  state_distribution: Record<string, number>;
  priorities: Array<{
    sub_cap_id: string;
    sub_cap_name: string;
    state?: string | null;
    score?: number | null;
    sow_count: number;
  }>;
};

// ─── Batch 5 ────────────────────────────────────────────────────────────────

export type BenchmarkVerdict = 'BENCHMARK' | 'INDICATIVE' | 'EXPLORATORY';

export type BenchmarkMetric = {
  metric_id: string;
  name: string;
  unit?: string;
  cohort_dimensions?: string[];
  primary_sources?: string[];
  secondary_sources?: string[];
  refresh_cadence?: string;
  subcap_mappings?: string[];
};

export type BenchmarkCohort = {
  cohort_id: string;
  name: string;
  subvertical?: string;
  asset_size_bucket?: string;
  business_model?: string;
  membership?: { asset_size_min_usd_bn?: number; asset_size_max_usd_bn?: number; subverticals?: string[] };
  notes?: string;
};

export type BenchmarkObservation = {
  id: string;
  company: string;
  subvertical?: string;
  asset_size_usd_bn?: number | null;
  metric_id: string;
  value: number;
  period: string;
  source_kind: 'filing' | 'analyst' | 'technographic' | 'ai_extrapolation';
  source_label: string;
  source_url?: string | null;
  evidence?: string;
  cohort_ids: string[];
  tier?: string;
  is_extrapolated: boolean;
  chain_id?: string;
  ingested_at: string;
};

export type BenchmarkDistribution = {
  id: string;
  metric_id: string;
  cohort_id: string;
  period: string;
  n: number;
  min: number | null;
  max: number | null;
  mean: number | null;
  stdev: number;
  p25: number;
  p50: number;
  p75: number;
  coef_var: number;
  verdict: BenchmarkVerdict;
  source_kinds: string[];
  observation_ids: string[];
  computed_at: string;
};

export type BenchmarkSource = {
  id: string;
  label: string;
  kind: string;
  tier?: string;
  observation_count: number;
  url?: string | null;
};

export type BenchmarksRefreshSummary = {
  run_id: string;
  started_at: string;
  completed_at: string;
  filings_loaded: number;
  analyst_observations: number;
  technographic_companies: number;
  observations_total: number;
  distributions_total: number;
  extrapolations_total: number;
  cohorts_loaded: number;
  sources: string[];
  schema_issues: string[];
};

// ─── Batch 4 ────────────────────────────────────────────────────────────────

export type ModelKind = 'gemini-flash' | 'gemini-pro' | 'sonnet' | 'opus';

export type GateResult = {
  name: string;
  verdict: 'pass' | 'warn' | 'fail';
  score: number;
  reasoning: string;
  details?: Record<string, unknown>;
};

export type ChainStep = {
  name: string;
  started_at: string;
  completed_at: string;
  model?: string | null;
  input_summary?: string;
  output_summary?: string;
  tokens_in?: number;
  tokens_out?: number;
  cost_usd?: number;
  cached?: boolean;
  detail?: Record<string, unknown>;
};

export type ReasoningChain = {
  chain_id: string;
  sub_cap_id: string | null;
  started_at: string;
  completed_at: string;
  overall: 'pass' | 'warn' | 'fail';
  total_cost_usd: number;
  output: { claims?: Array<{ text: string; subcap_id?: string; sources?: string[]; confidence?: number }> };
  sources: Array<{ id: string; kind?: string; title?: string; text?: string; url?: string | null; score?: number; published_at?: string }>;
  suggestions: Array<{ kind: string; target?: string; title?: string; rationale?: string }>;
  gates: { overall: string; score: number; results: GateResult[] };
  steps: ChainStep[];
};

export type Suggestion = {
  id: string;
  chain_id: string;
  sub_cap_id?: string | null;
  kind: string;
  target?: string | null;
  title?: string | null;
  rationale?: string | null;
  status: 'pending' | 'applied' | 'rejected';
  gate_overall?: string;
  created_at: string;
  decided_at?: string;
  decided_by?: string;
  reject_reason?: string | null;
};

export type SuggestionStats = { pending: number; applied: number; rejected: number; total: number };

export type NewsItem = {
  id: string;
  url: string | null;
  title: string;
  text: string;
  source: string;
  published_at: string;
  ingested_at: string;
  kind: 'news' | 'trend';
  subverticals?: string[];
  sub_cap_hits?: string[];
};

export type NewsIngestRun = {
  run_id: string;
  started_at: string;
  completed_at: string;
  news_loaded: number;
  trends_loaded: number;
  sources: string[];
  schema_issues: string[];
};

export type GateRunRow = {
  chain_id: string;
  sub_cap_id?: string | null;
  completed_at: string;
  overall: 'pass' | 'warn' | 'fail';
  score: number;
  results: GateResult[];
};

export type GateSummary = {
  total_runs: number;
  overall: Record<string, number>;
  by_gate: Record<string, Record<string, number>>;
  cost_summary: {
    today_usd: number;
    week_usd: number;
    today_calls: number;
    week_calls: number;
    by_model: Record<string, number>;
  };
};

// ─── Batch 3 ────────────────────────────────────────────────────────────────

export type SowStatus = 'active' | 'prospect' | 'inactive' | 'archived';

export type Sow = {
  sow_id: string;
  file_name: string;
  file_uri: string;
  status: SowStatus;
  source: 'local' | 'drive';
  ingested_at: string;
  client_name: string;
  client_raw?: string;
  client_confidence: number;
  page_count: number;
  char_count: number;
  chunk_count: number;
  mention_count: number;
  redaction_method: string;
  redaction_summary: Record<string, number>;
  extractor: string;
};

export type SowMention = {
  mention_id: string;
  sow_id: string;
  sub_cap_id: string;
  confidence: number;
  method: string;
  excerpt: string;
  client_name?: string;
  status?: SowStatus;
  ingested_at?: string;
};

export type SowDetail = { sow: Sow; mentions: SowMention[] };

export type SowPreview = {
  sow_id: string;
  file_name: string;
  redaction_method: string;
  redaction_summary: Record<string, number>;
  preview: string;
  truncated: boolean;
};

export type SowIngestRun = {
  run_id: string;
  started_at: string;
  completed_at: string;
  files_attempted: number;
  sows_loaded: number;
  chunks_total: number;
  mentions_total: number;
  redactions_total: number;
  sow_ids: string[];
};

export type StoriesIngestRun = {
  run_id: string;
  started_at: string;
  completed_at: string;
  canonical_loaded: number;
  jira_loaded: number;
  canonical_source?: string;
  jira_source?: string;
  schema_issues: string[];
};

export type CanonicalStory = {
  story_key: string;
  source_type?: string;
  pillar_id?: string;
  category_id?: string;
  cap_id?: string;
  sub_cap_id?: string;
  sub_cap_name?: string;
  tier?: string;
  reusability_layer?: string;
  population?: string;
  confidence_level?: string;
  confidence_score?: number;
  composite_score?: number;
  delivery_score?: number;
  ac_quality?: number;
  sd_quality?: number;
  summary?: string;
  description?: string;
  ac_text?: string;
  solution_design_text?: string;
};

export type JiraStory = {
  story_key: string;
  source_type?: string;
  summary?: string;
  status?: string;
  issue_type?: string;
  project_key?: string;
};

export type SubcapTrace = {
  sub_cap_id: string;
  sow_count: number;
  story_count: number;
  timeline: Array<
    | { kind: 'sow_mention'; sow_id: string; file_name: string; client_name: string; status: string; ingested_at: string; confidence: number; method: string; excerpt: string }
    | { kind: 'story'; story_key: string; source_type: string; summary: string; confidence?: string; composite_score?: number; ingested_at?: string }
  >;
};

export type Client = {
  client_id: string;
  name: string;
  first_seen: string;
  last_seen: string;
  sow_count: number;
  sow_ids: string[];
  statuses: SowStatus[];
};

// ─── Batch 2 ────────────────────────────────────────────────────────────────

export type GraphSummary = {
  snapshot_id: string;
  nodes_total: number;
  edges_total: number;
  nodes_by_type: Record<string, number>;
  edges_by_type: Record<string, number>;
};

export type GraphElements = {
  nodes: Array<{ data: Record<string, unknown> & { id: string; kind: string; label: string } }>;
  edges: Array<{ data: { id: string; source: string; target: string; kind: string } }>;
  truncated?: boolean;
};

export type CentralityRow = { id: string; label: string; kind: string; score: number };

export type Subvertical = { code: string; name: string };

export type VccCluster = { code: string; name: string; color?: string };

export type ValueChainAtlas = {
  subvertical_code?: string | null;
  clusters: Array<{
    code: string;
    name: string;
    color?: string;
    total_subcaps: number;
    stages: Array<{ name: string; subvertical_code: string; subcap_count: number; subcap_ids: string[] }>;
  }>;
};

export type SubverticalCompare = {
  sub_cap_id: string;
  rows: Array<{
    subvertical_code: string;
    subvertical_name: string;
    applicable: boolean;
    stages: Array<{ name: string; cluster: string }>;
  }>;
};

export type MaturityHeatmap = {
  pillar_id?: string | null;
  levels: string[];
  rows: Array<{
    sub_cap_id: string;
    sub_cap_name: string;
    category_id: string;
    l1_capability: string;
    cells: Array<{ level: string; filled: boolean; preview: string }>;
  }>;
};

export type UseCaseExplorer = {
  total_use_cases: number;
  families: Array<{
    family_id: string;
    family_name: string;
    color?: string;
    total: number;
    tags: Array<{ tag: string; count: number; examples: Array<{ use_case_id: string; sub_cap_id: string; description: string }> }>;
  }>;
};

export type PlatformCatalog = {
  total_platforms: number;
  vendors: Array<{
    vendor: string;
    platform_count: number;
    total_subcaps_using: number;
    platforms: Array<{ l3_id: string; name: string; category?: string; description?: string; reference_url?: string; subcap_count: number }>;
  }>;
};

export type ChangeFlag = {
  flag_id: string;
  kind: string;
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'BLOCKING';
  target_type: string;
  target_id: string;
  title: string;
  detail: string;
  detected_at: string;
  resolved_at?: string | null;
  resolved_by?: string | null;
  resolution_note?: string | null;
};
