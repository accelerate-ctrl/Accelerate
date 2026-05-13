import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { AlertTriangle, BookOpenCheck, History } from 'lucide-react';
import { apiGet, type Overview } from '@/lib/api';
import PillarRefreshPanel from '@/components/PillarRefreshPanel';

const PILLAR_ACCENT: Record<string, string> = {
  P1: 'border-zen-dark-green',
  P2: 'border-zen-dark-teal',
  P3: 'border-zen-teal',
  P4: 'border-zen-light-teal',
};

export default function MissionControl() {
  const { data, isLoading, error } = useQuery<Overview>({
    queryKey: ['overview'],
    queryFn: () => apiGet<Overview>('/catalogue/overview'),
  });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">Mission Control</h1>
        <p className="text-sm text-zen-dark-teal/80">
          State of the catalogue across the four pillars. Refresh sources to pull the latest from Drive.
        </p>
      </div>

      {isLoading && <div className="text-xs text-zen-dark-teal/60">Loading…</div>}
      {error && (
        <div className="text-xs text-zen-orange">
          Failed to load overview: {error instanceof Error ? error.message : 'unknown error'}.
          If this is a fresh deploy, click <b>Pull all sources</b> (top-right) once to ingest from
          Drive; this page populates after the catalogue ingest finishes.
        </div>
      )}
      {data && data.totals.pillars_loaded === 0 && (
        <div className="text-sm bg-zen-light-orange/40 border border-zen-orange/30 text-zen-dark-green rounded p-3">
          <b>No catalogue ingested yet.</b> Click <b>Pull all sources</b> (top-right) to fetch
          Pillar 1–4 workbooks from the configured Drive folder. The catalogue auto-picks the
          highest <code>vX.Y</code> version per pillar; "inactive" files are skipped.
        </div>
      )}

      {data && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <SummaryStat label="Pillars loaded" value={data.totals.pillars_loaded} sub="of 4" />
            <SummaryStat label="Subcaps" value={data.totals.subcaps} />
            <SummaryStat
              label="Open flags"
              value={data.totals.open_flags}
              sub={data.totals.open_flags > 0 ? 'needs review' : 'clean'}
              warn={data.totals.open_flags > 0}
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div>
              <h2 className="text-sm font-semibold text-zen-dark-green mb-2">Pillar tiles</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {(['P1', 'P2', 'P3', 'P4'] as const).map((pid) => {
                  const tile = data.pillars[pid];
                  return (
                    <div
                      key={pid}
                      className={`bg-white rounded-lg shadow-sm border-l-4 ${PILLAR_ACCENT[pid]} p-3`}
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-xs font-semibold text-zen-dark-teal/70">{pid}</div>
                          <div className="text-sm font-medium text-zen-dark-green">
                            {tile?.pillar.name || (pid === 'P1' ? 'Strategic Foundation' : 'awaiting input')}
                          </div>
                        </div>
                        {tile?.pillar.schema_status === 'incomplete' && (
                          <span className="text-[10px] uppercase bg-zen-light-orange text-zen-dark-green rounded px-1.5 py-0.5">
                            schema
                          </span>
                        )}
                      </div>
                      {tile ? (
                        <dl className="mt-2 grid grid-cols-3 gap-1 text-xs">
                          <Stat label="Categories" v={tile.category_count} />
                          <Stat label="Subcaps" v={tile.subcap_count} />
                          <Stat label="Active" v={tile.active_subcaps} />
                        </dl>
                      ) : (
                        <div className="mt-2 text-xs text-zen-dark-teal/60">
                          No file ingested yet. Upload a Pillar {pid.slice(1)} workbook with the
                          Pillar 1 schema to your Drive folder, then refresh.
                        </div>
                      )}
                      {tile?.pillar.source_version && (
                        <div className="mt-1.5 text-[10px] text-zen-dark-teal/60 truncate">
                          Source: {tile.pillar.source_file_name} ({tile.pillar.source_version})
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="space-y-3">
              <PillarRefreshPanel />

              <div className="bg-white rounded-lg shadow-sm border border-zen-light-green/40 p-4">
                <h2 className="text-sm font-semibold text-zen-dark-green flex items-center gap-2 mb-2">
                  <History size={16} /> Last ingest
                </h2>
                {data.last_ingest ? (
                  <div className="text-xs text-zen-dark-teal space-y-0.5">
                    <div>
                      <span className="font-mono text-[10px] text-zen-dark-teal/60">
                        {data.last_ingest.run_id}
                      </span>
                    </div>
                    <div>started: {new Date(data.last_ingest.started_at).toLocaleString()}</div>
                    <div>loaded: {data.last_ingest.pillars_loaded.join(', ') || '—'}</div>
                  </div>
                ) : (
                  <div className="text-xs text-zen-dark-teal/60">
                    No ingestions yet. Click Refresh all to ingest from Drive.
                  </div>
                )}
              </div>

              <div className="grid grid-cols-2 gap-2">
                <Link
                  to="/explorer"
                  className="block text-xs text-zen-dark-green bg-zen-light-green/40 hover:bg-zen-light-green/70 rounded p-2 text-center"
                >
                  <BookOpenCheck size={14} className="inline mr-1" /> Open Capability Explorer
                </Link>
                <Link
                  to="/flags"
                  className="block text-xs text-zen-dark-green bg-zen-light-green/40 hover:bg-zen-light-green/70 rounded p-2 text-center"
                >
                  <AlertTriangle size={14} className="inline mr-1" /> Review flags
                </Link>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function SummaryStat({ label, value, sub, warn }: { label: string; value: number; sub?: string; warn?: boolean }) {
  return (
    <div className="bg-white rounded-lg shadow-sm border border-zen-light-green/40 p-4">
      <div className="text-xs text-zen-dark-teal/70">{label}</div>
      <div className={`text-2xl font-semibold ${warn ? 'text-zen-orange' : 'text-zen-dark-green'}`}>{value}</div>
      {sub && <div className="text-xs text-zen-dark-teal/60">{sub}</div>}
    </div>
  );
}

function Stat({ label, v }: { label: string; v: number }) {
  return (
    <div>
      <div className="text-zen-dark-teal/60 text-[10px] uppercase tracking-wider">{label}</div>
      <div className="font-mono text-zen-dark-green">{v}</div>
    </div>
  );
}
