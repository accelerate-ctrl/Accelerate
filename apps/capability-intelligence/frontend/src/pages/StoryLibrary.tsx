import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { CheckCircle2, RefreshCw } from 'lucide-react';
import { apiGet, apiPost, type CanonicalStory, type JiraStory, type StoriesIngestRun } from '@/lib/api';

export default function StoryLibrary() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState('');

  const { data: canonical, isLoading: loadingC } = useQuery<CanonicalStory[]>({
    queryKey: ['stories-canonical'],
    queryFn: () => apiGet<CanonicalStory[]>('/stories/canonical?limit=100'),
  });

  const { data: jira, isLoading: loadingJ } = useQuery<JiraStory[]>({
    queryKey: ['stories-jira'],
    queryFn: () => apiGet<JiraStory[]>('/stories/jira?limit=100'),
  });

  const refresh = useMutation({
    mutationFn: () => apiPost<StoriesIngestRun>('/stories/refresh'),
    onSettled: () => qc.invalidateQueries(),
  });

  const visibleCanonical = (canonical || []).filter(
    (s) =>
      !filter ||
      s.story_key.toLowerCase().includes(filter.toLowerCase()) ||
      (s.summary || '').toLowerCase().includes(filter.toLowerCase()) ||
      (s.sub_cap_id || '').toLowerCase().includes(filter.toLowerCase()),
  );

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zen-dark-green">Story Library</h1>
          <p className="text-sm text-zen-dark-teal/80">
            Canonical stories from <span className="font-mono">gen_stories_export.xlsx</span> (rich quality scores) on the
            left; live Jira stories on the right (active when Atlassian creds are configured).
          </p>
        </div>
        <button
          type="button"
          onClick={() => refresh.mutate()}
          disabled={refresh.isPending}
          className="bg-zen-teal hover:bg-zen-dark-teal text-white text-xs font-medium px-3 py-1.5 rounded transition-colors disabled:opacity-50"
        >
          <RefreshCw size={12} className={`inline mr-1 ${refresh.isPending ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      {refresh.data && (
        <div className="bg-white border border-zen-light-green/40 rounded-lg p-3 text-xs text-zen-dark-teal flex items-start gap-2">
          <CheckCircle2 size={14} className="text-zen-teal mt-0.5" />
          <div>
            Canonical: <strong>{refresh.data.canonical_loaded}</strong> stories from{' '}
            <span className="font-mono">{refresh.data.canonical_source || 'n/a'}</span>. Jira:{' '}
            <strong>{refresh.data.jira_loaded}</strong> issues from{' '}
            <span className="font-mono">{refresh.data.jira_source || 'not configured'}</span>.
            {refresh.data.schema_issues.length > 0 && (
              <div className="mt-1 text-zen-orange">Issues: {refresh.data.schema_issues.join('; ')}</div>
            )}
          </div>
        </div>
      )}

      <div className="bg-white rounded-lg border border-zen-light-green/40 p-2">
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter by story key, sub_cap_id, or summary…"
          className="w-full text-sm bg-transparent outline-none placeholder:text-zen-dark-teal/50"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div className="bg-white rounded-lg border border-zen-light-green/40 p-3">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-zen-dark-green">
              Canonical (gen_stories)
            </h2>
            <span className="text-xs text-zen-dark-teal/60">{(canonical || []).length} loaded</span>
          </div>
          {loadingC && <div className="text-xs text-zen-dark-teal/60">Loading…</div>}
          <ul className="divide-y divide-zen-light-green/20 max-h-[640px] overflow-auto">
            {visibleCanonical.slice(0, 100).map((s) => (
              <li key={s.story_key} className="py-1.5 text-xs">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[10px] text-zen-dark-teal/60">{s.story_key}</span>
                  {s.sub_cap_id && (
                    <Link to={`/subcap?id=${encodeURIComponent(s.sub_cap_id)}`} className="font-mono text-[10px] bg-zen-light-green/50 text-zen-dark-teal px-1 rounded hover:text-zen-dark-green">
                      {s.sub_cap_id}
                    </Link>
                  )}
                  {s.confidence_level && (
                    <span className={`text-[9px] uppercase rounded px-1 ${s.confidence_level === 'HIGH' ? 'bg-zen-teal text-white' : 'bg-zen-light-orange text-zen-dark-green'}`}>
                      {s.confidence_level}
                    </span>
                  )}
                </div>
                <div className="text-zen-dark-teal mt-0.5">{s.summary?.slice(0, 240)}</div>
                {(s.composite_score != null || s.ac_quality != null || s.sd_quality != null) && (
                  <div className="text-[10px] text-zen-dark-teal/70 mt-0.5 flex gap-2">
                    {s.composite_score != null && <span>composite={s.composite_score}</span>}
                    {s.ac_quality != null && <span>ac={s.ac_quality}</span>}
                    {s.sd_quality != null && <span>sd={s.sd_quality}</span>}
                    {s.delivery_score != null && <span>delivery={s.delivery_score}</span>}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>

        <div className="bg-white rounded-lg border border-zen-light-green/40 p-3">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-zen-dark-green">Jira (live)</h2>
            <span className="text-xs text-zen-dark-teal/60">{(jira || []).length} loaded</span>
          </div>
          {loadingJ && <div className="text-xs text-zen-dark-teal/60">Loading…</div>}
          {(jira || []).length === 0 ? (
            <div className="text-xs text-zen-dark-teal/70 bg-zen-white-green rounded p-2">
              Atlassian creds not configured. Live Jira sync activates when{' '}
              <span className="font-mono">JIRA_BASE_URL</span> + email/token are set.
            </div>
          ) : (
            <ul className="divide-y divide-zen-light-green/20 max-h-[640px] overflow-auto">
              {(jira || []).slice(0, 100).map((s) => (
                <li key={s.story_key} className="py-1.5 text-xs">
                  <div className="font-mono text-[10px] text-zen-dark-teal/70">{s.story_key}</div>
                  <div className="text-zen-dark-teal">{s.summary}</div>
                  <div className="text-[10px] text-zen-dark-teal/60 mt-0.5">{s.status} · {s.issue_type}</div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
