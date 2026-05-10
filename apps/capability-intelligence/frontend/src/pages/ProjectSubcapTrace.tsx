import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams, Link } from 'react-router-dom';
import { Briefcase, BookOpenCheck } from 'lucide-react';
import { apiGet, type Subcap, type SubcapTrace } from '@/lib/api';

export default function ProjectSubcapTrace() {
  const [params, setParams] = useSearchParams();
  const initial = params.get('id') || 'P1C1.1.1';
  const [id, setId] = useState(initial);

  const { data: subcaps } = useQuery<Subcap[]>({
    queryKey: ['subcaps-list'],
    queryFn: () => apiGet<Subcap[]>('/catalogue/subcaps'),
  });

  const { data, isLoading } = useQuery<SubcapTrace>({
    queryKey: ['trace', id],
    queryFn: () => apiGet<SubcapTrace>(`/projects/subcap-trace?sub_cap_id=${encodeURIComponent(id)}`),
    enabled: !!id,
  });

  const onSelect = (newId: string) => {
    setId(newId);
    setParams({ id: newId });
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">Project–Subcap Trace</h1>
        <p className="text-sm text-zen-dark-teal/80">
          For a given subcap, show every SOW + story that touched it, in time order.
        </p>
      </div>

      <div className="bg-white rounded-lg border border-zen-light-green/40 p-3 flex items-center gap-2 text-sm">
        <label className="text-zen-dark-teal/70">Subcap</label>
        <select
          value={id}
          onChange={(e) => onSelect(e.target.value)}
          className="border border-zen-light-green rounded px-2 py-1 text-xs flex-1 max-w-md"
        >
          {subcaps?.slice(0, 500).map((s) => (
            <option key={s.sub_cap_id} value={s.sub_cap_id}>
              {s.sub_cap_id} — {s.sub_cap_name}
            </option>
          ))}
        </select>
        {data && (
          <div className="text-xs text-zen-dark-teal ml-auto">
            <strong>{data.sow_count}</strong> SOWs · <strong>{data.story_count}</strong> stories
          </div>
        )}
      </div>

      {isLoading && <div className="text-xs text-zen-dark-teal/60">Loading…</div>}

      {data && (
        <div className="bg-white rounded-lg border border-zen-light-green/40 p-3">
          {data.timeline.length === 0 ? (
            <div className="text-xs text-zen-dark-teal/60 italic">No SOWs or stories touch this subcap yet.</div>
          ) : (
            <ol className="relative border-l-2 border-zen-light-green/40 ml-2 space-y-3">
              {data.timeline.map((t, i) => (
                <li key={i} className="ml-4">
                  <div className="absolute -left-[7px] mt-1 w-3 h-3 rounded-full bg-zen-teal border-2 border-white" />
                  {t.kind === 'sow_mention' ? (
                    <div className="text-xs">
                      <div className="flex items-center gap-2 text-zen-dark-green font-medium">
                        <Briefcase size={12} className="text-zen-teal" />
                        <span>{t.client_name}</span>
                        <span className="text-[10px] uppercase rounded px-1 bg-zen-light-green/60 text-zen-dark-teal">
                          {t.status}
                        </span>
                      </div>
                      <div className="text-zen-dark-teal mt-0.5">
                        <Link to={`/sows`} className="font-mono text-[10px] hover:text-zen-dark-green underline mr-2">
                          {t.sow_id}
                        </Link>
                        {t.file_name}
                      </div>
                      <div className="text-[10px] text-zen-dark-teal/70 mt-0.5">
                        {t.method} · confidence {t.confidence.toFixed(0)} · {new Date(t.ingested_at).toLocaleString()}
                      </div>
                      <div className="text-zen-dark-teal mt-1 italic bg-zen-white-green/60 px-2 py-1 rounded">
                        “{t.excerpt}”
                      </div>
                    </div>
                  ) : (
                    <div className="text-xs">
                      <div className="flex items-center gap-2 text-zen-dark-green font-medium">
                        <BookOpenCheck size={12} className="text-zen-teal" />
                        <span className="font-mono text-[10px]">{t.story_key}</span>
                        <span className="text-[10px] uppercase rounded px-1 bg-zen-light-green/60 text-zen-dark-teal">
                          {t.source_type}
                        </span>
                        {t.confidence && (
                          <span className="text-[10px] uppercase rounded px-1 bg-zen-light-orange text-zen-dark-green">
                            {t.confidence}
                          </span>
                        )}
                      </div>
                      <div className="text-zen-dark-teal mt-0.5">{t.summary?.slice(0, 220)}</div>
                      {t.composite_score != null && (
                        <div className="text-[10px] text-zen-dark-teal/70 mt-0.5">
                          composite={t.composite_score}
                        </div>
                      )}
                    </div>
                  )}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}
