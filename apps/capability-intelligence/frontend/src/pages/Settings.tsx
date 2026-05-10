import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';

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
  const { data } = useQuery<EffectiveSettings>({
    queryKey: ['settings'],
    queryFn: () => apiGet<EffectiveSettings>('/settings'),
  });

  return (
    <div className="space-y-4 max-w-3xl">
      <div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">Settings</h1>
        <p className="text-sm text-zen-dark-teal/80">
          Effective configuration. Most values come from environment variables / Secret Manager.
        </p>
      </div>

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

      <div className="bg-zen-white-green rounded-lg border border-zen-light-green/40 p-4 text-xs text-zen-dark-teal">
        <div className="font-semibold text-zen-dark-green mb-1">Mutable Settings UI: Batch 8</div>
        Editable controls for canonical sources, personas, and feature flags ship in Batch 8. For
        now, change values via <span className="font-mono">.env</span> and restart the service.
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
