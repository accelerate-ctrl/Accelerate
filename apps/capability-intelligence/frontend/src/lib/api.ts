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
