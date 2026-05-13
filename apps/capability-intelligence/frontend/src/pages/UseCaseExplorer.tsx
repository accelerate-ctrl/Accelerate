import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { apiGet, type UseCaseExplorer as UCE } from '@/lib/api';

export default function UseCaseExplorer() {
  const [familyId, setFamilyId] = useState<string | null>(null);
  const [tag, setTag] = useState<string | null>(null);
  const [search, setSearch] = useState('');

  const { data, isLoading } = useQuery<UCE>({
    queryKey: ['uc-explorer'],
    queryFn: () => apiGet<UCE>('/lens/use-case-explorer'),
  });

  const families = data?.families || [];
  const activeFamily = useMemo(
    () => families.find((f) => f.family_id === familyId) || families[0] || null,
    [families, familyId],
  );

  const filteredTags = useMemo(() => {
    const tags = activeFamily?.tags || [];
    if (!search.trim()) return tags;
    const q = search.toLowerCase();
    return tags.filter(
      (t) =>
        t.tag.toLowerCase().includes(q) ||
        t.examples.some((e) => e.description?.toLowerCase().includes(q)),
    );
  }, [activeFamily, search]);

  const activeTag = useMemo(
    () => filteredTags.find((t) => t.tag === tag) || filteredTags[0] || null,
    [filteredTags, tag],
  );

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">Use Case Explorer</h1>
        <p className="text-sm text-zen-dark-teal/80 max-w-3xl">
          Every use case across the catalogue, grouped by 22 archetype tags in 5 families
          (Strategic, Workflow, Communication, Governance & Risk, Reporting & Validation).
          Pick a family at the top, a tag on the left, then click any subcap to drill in.
        </p>
      </div>

      {isLoading && <div className="text-xs text-zen-muted-text">Loading…</div>}

      {data && (
        <>
          {/* Family selector — horizontal pills */}
          <div className="flex flex-wrap gap-2">
            {families.map((f) => {
              const isActive = (familyId ?? families[0]?.family_id) === f.family_id;
              return (
                <button
                  key={f.family_id}
                  type="button"
                  onClick={() => {
                    setFamilyId(f.family_id);
                    setTag(null);
                  }}
                  className={[
                    'rounded-lg border px-3 py-2 text-left transition',
                    isActive
                      ? 'border-zen-teal bg-white shadow-sm'
                      : 'border-zen-separator bg-white hover:border-zen-teal/40',
                  ].join(' ')}
                  style={{ borderLeftWidth: 4, borderLeftColor: f.color || '#27BBAF' }}
                >
                  <div className="text-sm font-semibold text-zen-dark-green">{f.family_name}</div>
                  <div className="text-[10px] text-zen-muted-text">
                    {f.tags.length} tags · {f.total} use cases
                  </div>
                </button>
              );
            })}
          </div>

          {/* Search */}
          <div className="bg-white rounded-lg border border-zen-separator p-2">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter tags / use-case descriptions…"
              className="w-full bg-transparent text-sm outline-none placeholder:text-zen-muted-text"
            />
          </div>

          {/* Master/detail */}
          {activeFamily && (
            <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-3">
              {/* Left: tag list */}
              <div className="bg-white rounded-lg border border-zen-separator overflow-hidden flex flex-col max-h-[560px]">
                <div className="px-3 py-2 border-b border-zen-separator text-[10px] uppercase tracking-wider text-zen-muted-text">
                  {activeFamily.family_name} tags
                </div>
                <ul className="divide-y divide-zen-separator/40 overflow-auto">
                  {filteredTags.map((t) => {
                    const isActive = activeTag?.tag === t.tag;
                    return (
                      <li key={t.tag}>
                        <button
                          type="button"
                          onClick={() => setTag(t.tag)}
                          className={[
                            'w-full text-left px-3 py-2 transition flex items-baseline gap-2',
                            isActive ? 'bg-zen-ice' : 'hover:bg-zen-ice/40',
                          ].join(' ')}
                        >
                          <span className="text-xs font-mono text-zen-teal flex-1 truncate">{t.tag}</span>
                          <span className="text-[10px] text-zen-muted-text">×{t.count}</span>
                        </button>
                      </li>
                    );
                  })}
                  {filteredTags.length === 0 && (
                    <li className="text-xs text-zen-muted-text italic px-3 py-3">
                      No tags match "{search}".
                    </li>
                  )}
                </ul>
              </div>

              {/* Right: use cases for active tag */}
              <div className="bg-white rounded-lg border border-zen-separator p-3">
                {activeTag ? (
                  <>
                    <div className="flex items-baseline gap-2 mb-2">
                      <h3 className="text-sm font-semibold text-zen-dark-green">
                        <span className="font-mono text-xs text-zen-teal mr-2">{activeTag.tag}</span>
                      </h3>
                      <span className="text-xs text-zen-muted-text">
                        {activeTag.count} use case{activeTag.count === 1 ? '' : 's'}
                      </span>
                    </div>
                    <ul className="divide-y divide-zen-separator/40">
                      {activeTag.examples.map((e) => (
                        <li key={e.use_case_id} className="py-2">
                          <Link
                            to={`/subcap?id=${encodeURIComponent(e.sub_cap_id)}`}
                            className="block hover:bg-zen-ice/40 -m-2 p-2 rounded"
                          >
                            <div className="flex items-baseline gap-2 mb-0.5">
                              <span className="font-mono text-[10px] text-zen-muted-text">
                                {e.use_case_id}
                              </span>
                              <span className="font-mono text-[10px] bg-zen-light-green/60 text-zen-dark-teal rounded px-1">
                                {e.sub_cap_id}
                              </span>
                            </div>
                            <p className="text-xs text-zen-dark-green leading-snug">
                              {e.description || '(no description)'}
                            </p>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </>
                ) : (
                  <div className="text-xs text-zen-muted-text italic">
                    Select a tag on the left.
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
