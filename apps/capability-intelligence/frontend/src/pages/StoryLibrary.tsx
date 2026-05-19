import { useState, useEffect, useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { CheckCircle2, Loader2, RefreshCw } from 'lucide-react';
import {
  apiGet,
  apiPost,
  type CanonicalStory,
  type JiraStory,
  type StoriesIngestRun,
  type StoriesPage,
} from '@/lib/api';

const PAGE_SIZE = 100;

export default function StoryLibrary() {
  const qc = useQueryClient();
  const [rawFilter, setRawFilter] = useState('');
  const [filter, setFilter] = useState('');
  const [canonicalCount, setCanonicalCount] = useState(PAGE_SIZE);
  const [jiraCount, setJiraCount] = useState(PAGE_SIZE);

  // Debounce so each keystroke doesn't re-hit the API.
  useEffect(() => {
    const t = window.setTimeout(() => setFilter(rawFilter.trim()), 200);
    return () => window.clearTimeout(t);
  }, [rawFilter]);

  // Reset the displayed window when the filter changes so we don't show
  // a stale offset against a different result set.
  useEffect(() => {
    setCanonicalCount(PAGE_SIZE);
    setJiraCount(PAGE_SIZE);
  }, [filter]);

  const canonicalQs = useMemo(() => {
    const p = new URLSearchParams({
      offset: '0',
      limit: String(canonicalCount),
    });
    if (filter) p.set('q', filter);
    return p.toString();
  }, [filter, canonicalCount]);

  const jiraQs = useMemo(() => {
    const p = new URLSearchParams({
      offset: '0',
      limit: String(jiraCount),
    });
    if (filter) p.set('q', filter);
    return p.toString();
  }, [filter, jiraCount]);

  const canonical = useQuery<StoriesPage<CanonicalStory>>({
    queryKey: ['stories-canonical-paged', filter, canonicalCount],
    queryFn: () =>
      apiGet<StoriesPage<CanonicalStory>>(`/stories/canonical/paged?${canonicalQs}`),
  });

  const jira = useQuery<StoriesPage<JiraStory>>({
    queryKey: ['stories-jira-paged', filter, jiraCount],
    queryFn: () => apiGet<StoriesPage<JiraStory>>(`/stories/jira/paged?${jiraQs}`),
  });

  const refresh = useMutation({
    mutationFn: () => apiPost<StoriesIngestRun>('/stories/refresh'),
    onSettled: () => qc.invalidateQueries(),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zen-dark-green">Story Library</h1>
          <p className="text-sm text-zen-dark-teal/80">
            Canonical stories from{' '}
            <span className="font-mono">gen_stories_export.xlsx</span> (rich quality
            scores) on the left; live Jira stories on the right (active when Atlassian
            creds are configured). Server-side filter searches the full corpus.
          </p>
        </div>
        <button
          type="button"
          onClick={() => refresh.mutate()}
          disabled={refresh.isPending}
          className="bg-zen-teal hover:bg-zen-dark-teal text-white text-xs font-medium px-3 py-1.5 rounded transition-colors disabled:opacity-50"
        >
          <RefreshCw size={12} className={`inline mr-1 ${refresh.isPending ? 'animate-spin' : ''}`} />{' '}
          Refresh
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
              <div className="mt-1 text-zen-orange">
                Issues: {refresh.data.schema_issues.join('; ')}
              </div>
            )}
          </div>
        </div>
      )}

      <div className="bg-white rounded-lg border border-zen-light-green/40 p-2">
        <input
          type="text"
          value={rawFilter}
          onChange={(e) => setRawFilter(e.target.value)}
          placeholder="Filter the full corpus by story key, sub_cap_id, or summary…"
          className="w-full text-sm bg-transparent outline-none placeholder:text-zen-dark-teal/50"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <PagedColumn
          title="Canonical (gen_stories)"
          page={canonical.data}
          isLoading={canonical.isLoading}
          isFetching={canonical.isFetching}
          onLoadMore={() => setCanonicalCount((c) => c + PAGE_SIZE)}
          renderRow={(s) => <CanonicalRow s={s} key={s.story_key} />}
        />
        <PagedColumn
          title="Jira (live)"
          page={jira.data}
          isLoading={jira.isLoading}
          isFetching={jira.isFetching}
          onLoadMore={() => setJiraCount((c) => c + PAGE_SIZE)}
          emptyMessage={
            <>
              Atlassian creds not configured. Live Jira sync activates when{' '}
              <span className="font-mono">JIRA_BASE_URL</span> + email/token are set.
            </>
          }
          renderRow={(s) => <JiraRow s={s} key={s.story_key} />}
        />
      </div>
    </div>
  );
}

function PagedColumn<T extends { story_key: string }>({
  title,
  page,
  isLoading,
  isFetching,
  onLoadMore,
  renderRow,
  emptyMessage,
}: {
  title: string;
  page: StoriesPage<T> | undefined;
  isLoading: boolean;
  isFetching: boolean;
  onLoadMore: () => void;
  renderRow: (s: T) => React.ReactNode;
  emptyMessage?: React.ReactNode;
}) {
  const rows = page?.rows ?? [];
  const total = page?.total ?? 0;
  const hasMore = rows.length < total;
  return (
    <div className="bg-white rounded-lg border border-zen-light-green/40 p-3">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-zen-dark-green">
          {title}
        </h2>
        <span className="text-xs text-zen-dark-teal/60">
          {rows.length.toLocaleString()} / {total.toLocaleString()}
        </span>
      </div>
      {isLoading && (
        <div className="text-xs text-zen-dark-teal/60 flex items-center gap-1">
          <Loader2 size={12} className="animate-spin" /> Loading…
        </div>
      )}
      {!isLoading && rows.length === 0 && (
        <div className="text-xs text-zen-dark-teal/70 bg-zen-white-green rounded p-2">
          {emptyMessage ?? 'No matches.'}
        </div>
      )}
      {rows.length > 0 && (
        <>
          <ul className="divide-y divide-zen-light-green/20 max-h-[640px] overflow-auto">
            {rows.map(renderRow)}
          </ul>
          {hasMore && (
            <button
              type="button"
              onClick={onLoadMore}
              disabled={isFetching}
              className="mt-2 w-full text-xs bg-zen-ice hover:bg-zen-light-green/40 text-zen-dark-green rounded py-1.5 transition-colors disabled:opacity-50 flex items-center justify-center gap-1"
            >
              {isFetching && <Loader2 size={10} className="animate-spin" />}
              Load more · {(total - rows.length).toLocaleString()} remaining
            </button>
          )}
        </>
      )}
    </div>
  );
}

function CanonicalRow({ s }: { s: CanonicalStory }) {
  return (
    <li className="py-1.5 text-xs">
      <div className="flex items-center gap-2">
        <span className="font-mono text-[10px] text-zen-dark-teal/60">{s.story_key}</span>
        {s.sub_cap_id && (
          <Link
            to={`/subcap?id=${encodeURIComponent(s.sub_cap_id)}`}
            className="font-mono text-[10px] bg-zen-light-green/50 text-zen-dark-teal px-1 rounded hover:text-zen-dark-green"
          >
            {s.sub_cap_id}
          </Link>
        )}
        {s.confidence_level && (
          <span
            className={`text-[9px] uppercase rounded px-1 ${
              s.confidence_level === 'HIGH'
                ? 'bg-zen-teal text-white'
                : 'bg-zen-light-orange text-zen-dark-green'
            }`}
          >
            {s.confidence_level}
          </span>
        )}
      </div>
      <div className="text-zen-dark-teal mt-0.5">{s.summary?.slice(0, 240)}</div>
      {(s.composite_score != null ||
        s.ac_quality != null ||
        s.sd_quality != null) && (
        <div className="text-[10px] text-zen-dark-teal/70 mt-0.5 flex gap-2">
          {s.composite_score != null && <span>composite={s.composite_score}</span>}
          {s.ac_quality != null && <span>ac={s.ac_quality}</span>}
          {s.sd_quality != null && <span>sd={s.sd_quality}</span>}
          {s.delivery_score != null && <span>delivery={s.delivery_score}</span>}
        </div>
      )}
    </li>
  );
}

function JiraRow({ s }: { s: JiraStory }) {
  return (
    <li className="py-1.5 text-xs">
      <div className="font-mono text-[10px] text-zen-dark-teal/70">{s.story_key}</div>
      <div className="text-zen-dark-teal">{s.summary}</div>
      <div className="text-[10px] text-zen-dark-teal/60 mt-0.5">
        {s.status} · {s.issue_type}
      </div>
    </li>
  );
}
