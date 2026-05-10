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
