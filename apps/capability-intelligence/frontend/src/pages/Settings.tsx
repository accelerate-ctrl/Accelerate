import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, type CatalogueState } from '@/lib/api';
import PillarUploadDropZone from '@/components/PillarUploadDropZone';

type EffectiveSettings = {
  env: string;
  auth_mode: string;
  auth_allowed_domain: string;
  use_gcp: boolean;
  gcp_project_id: string | null;
  gcp_region: string;
  firestore_database_id: string;
  drive_pillars_folder_id: string | null;
  local_catalogue_dir: string | null;
  daily_spend_ceiling_usd: number;
  anthropic_weekly_budget_usd: number;
};

export default function SettingsPage() {
  const qc = useQueryClient();
  const { data } = useQuery<EffectiveSettings>({
    queryKey: ['settings'],
    queryFn: () => apiGet<EffectiveSettings>('/settings'),
  });
  const { data: state } = useQuery<CatalogueState>({
    queryKey: ['catalogue-state'],
    queryFn: () => apiGet<CatalogueState>('/sheets/state'),
    refetchInterval: 30_000,
  });

  return (
    <div className="space-y-4 max-w-3xl">
      <div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">Settings</h1>
        <p className="text-sm text-zen-dark-teal/80">
          Effective configuration. Most values come from environment variables / Secret Manager.
        </p>
      </div>

      <section className="bg-white rounded-lg shadow-sm border border-zen-light-green/40 p-4 space-y-3">
        <div>
          <h2 className="text-base font-semibold text-zen-dark-green">Pillar workbooks</h2>
          <p className="text-xs text-zen-dark-teal/70">
            Drop the canonical v7.0 .xlsx for each pillar. Used while Drive
            copies are pending pillar-lead approval; once approved, the Drive
            poller will pick them up automatically every 6 hours. Each upload
            replaces that pillar's slice of the catalogue and broadcasts to
            all active sessions.
          </p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
          {(state?.pillars || []).map((p) => (
            <PillarUploadDropZone
              key={p.pillar_id}
              pillar={p}
              onUploaded={() => {
                void qc.invalidateQueries({ queryKey: ['catalogue-state'] });
                void qc.invalidateQueries({ queryKey: ['overview'] });
                void qc.invalidateQueries({ queryKey: ['catalogue-tree'] });
                void qc.invalidateQueries({ queryKey: ['catalogue-structure'] });
              }}
            />
          ))}
        </div>
      </section>

      {data && (
        <div className="bg-white rounded-lg shadow-sm border border-zen-light-green/40 p-4 grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
          <Field label="Environment" value={data.env} />
          <Field label="Auth mode" value={data.auth_mode} />
          <Field label="Allowed sign-in domain" value={data.auth_allowed_domain} />
          <Field label="GCP enabled" value={data.use_gcp ? 'yes' : 'no'} />
          <Field label="GCP project" value={data.gcp_project_id || '—'} />
          <Field label="GCP region" value={data.gcp_region} />
          <Field label="Firestore database" value={data.firestore_database_id} />
          <Field label="Drive pillars folder" value={data.drive_pillars_folder_id || '—'} mono />
          <Field label="Local catalogue dir" value={data.local_catalogue_dir || '—'} mono />
          <Field label="Daily spend ceiling (USD)" value={String(data.daily_spend_ceiling_usd || '0 = disabled')} />
          <Field label="Anthropic weekly budget (USD)" value={String(data.anthropic_weekly_budget_usd || '0 = disabled')} />
        </div>
      )}

      <div className="bg-zen-ice rounded-lg border border-zen-separator p-4 text-xs text-zen-dark-teal">
        <div className="font-semibold text-zen-dark-green mb-1">Mutable settings UI — coming soon</div>
        Editable controls for canonical sources, personas, and feature flags are on the
        roadmap. For now, change values via <span className="font-mono">infra/service.yaml</span> and
        redeploy.
      </div>
    </div>
  );
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-zen-dark-teal/70">{label}</div>
      <div className={`text-zen-dark-green ${mono ? 'font-mono text-xs' : ''}`}>{value}</div>
    </div>
  );
}
