import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { GitCommit, Save } from 'lucide-react';
import { apiGet, apiPost, type CatalogueVersion } from '@/lib/api';

export default function VersionTimeline() {
  const qc = useQueryClient();
  const [label, setLabel] = useState('');
  const [summary, setSummary] = useState('');

  const { data: versions } = useQuery<CatalogueVersion[]>({
    queryKey: ['versions'],
    queryFn: () => apiGet<CatalogueVersion[]>('/versions'),
  });

  const save = useMutation({
    mutationFn: () => apiPost<CatalogueVersion>('/versions', { label, summary }),
    onSuccess: () => {
      setLabel('');
      setSummary('');
      qc.invalidateQueries({ queryKey: ['versions'] });
    },
  });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">Version Timeline</h1>
        <p className="text-sm text-zen-dark-teal/80">
          Every save is a snapshot; diffs and rollbacks reference these IDs.
        </p>
      </div>

      <div className="bg-white rounded-lg shadow-sm border border-zen-light-green/40 p-3">
        <h2 className="text-xs font-semibold text-zen-dark-green uppercase tracking-wider mb-2">
          Save current state as a new version
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Label (optional)"
            className="border border-zen-light-green rounded px-2 py-1 text-sm flex-1 min-w-[180px]"
          />
          <input
            type="text"
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            placeholder="One-line summary (optional)"
            className="border border-zen-light-green rounded px-2 py-1 text-sm flex-[2] min-w-[260px]"
          />
          <button
            type="button"
            onClick={() => save.mutate()}
            disabled={save.isPending}
            className="bg-zen-teal hover:bg-zen-dark-teal text-white text-sm px-3 py-1.5 rounded disabled:opacity-50"
          >
            <Save size={14} className="inline mr-1" /> Save version
          </button>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow-sm border border-zen-light-green/40 p-3">
        <h2 className="text-xs font-semibold text-zen-dark-green uppercase tracking-wider mb-2">History</h2>
        {!versions || versions.length === 0 ? (
          <div className="text-xs text-zen-dark-teal/70">No versions saved yet.</div>
        ) : (
          <ul className="divide-y divide-zen-light-green/30">
            {versions.map((v) => (
              <li key={v.version_id} className="py-2 flex items-start gap-2">
                <GitCommit size={16} className={v.is_current ? 'text-zen-teal mt-0.5' : 'text-zen-dark-teal/50 mt-0.5'} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 text-sm">
                    <span className="font-mono text-xs text-zen-dark-teal">{v.version_id}</span>
                    {v.is_current && (
                      <span className="text-[10px] uppercase bg-zen-teal/30 text-zen-dark-green rounded px-1.5 py-0.5">
                        current
                      </span>
                    )}
                    {v.label && <span className="text-zen-dark-green font-medium">{v.label}</span>}
                  </div>
                  <div className="text-xs text-zen-dark-teal/80 mt-0.5">{v.summary}</div>
                  <div className="text-[10px] text-zen-dark-teal/60 mt-0.5">
                    {new Date(v.created_at).toLocaleString()} · by {v.created_by} · pillar counts:{' '}
                    {Object.entries(v.pillar_counts)
                      .map(([k, n]) => `${k}=${n}`)
                      .join(', ')}
                  </div>
                </div>
                <Link
                  to={`/diff?b=${v.version_id}`}
                  className="text-xs text-zen-teal hover:text-zen-dark-teal underline shrink-0"
                >
                  Diff →
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
