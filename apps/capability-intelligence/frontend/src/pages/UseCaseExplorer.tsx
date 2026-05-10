import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { apiGet, type UseCaseExplorer as UCE } from '@/lib/api';

export default function UseCaseExplorer() {
  const { data, isLoading } = useQuery<UCE>({
    queryKey: ['uc-explorer'],
    queryFn: () => apiGet<UCE>('/lens/use-case-explorer'),
  });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">Use Case Explorer</h1>
        <p className="text-sm text-zen-dark-teal/80">
          Use cases grouped by 22 archetype tags across 5 families: Strategic, Workflow,
          Communication, Governance & Risk, Reporting & Validation.
        </p>
      </div>

      {isLoading && <div className="text-xs text-zen-dark-teal/60">Loading…</div>}

      {data && (
        <>
          <div className="text-sm text-zen-dark-teal">
            Total tagged use cases: <span className="font-mono font-semibold">{data.total_use_cases}</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {data.families.map((fam) => (
              <div
                key={fam.family_id}
                className="bg-white rounded-lg border border-zen-light-green/40 p-3"
                style={{ borderLeftWidth: 4, borderLeftColor: fam.color || '#27bbaf' }}
              >
                <div className="flex items-center justify-between">
                  <div className="text-sm font-semibold text-zen-dark-green">{fam.family_name}</div>
                  <div className="text-xs text-zen-dark-teal/60">{fam.total} UCs</div>
                </div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {fam.tags.map((t) => (
                    <span
                      key={t.tag}
                      className="text-[10px] uppercase tracking-wider bg-zen-light-green/40 text-zen-dark-teal rounded px-1.5 py-0.5"
                      title={t.examples.map((e) => `${e.sub_cap_id}: ${e.description}`).join('\n\n')}
                    >
                      {t.tag} <span className="opacity-70">×{t.count}</span>
                    </span>
                  ))}
                </div>
                <details className="mt-2 text-xs">
                  <summary className="cursor-pointer text-zen-dark-teal hover:text-zen-dark-green">
                    Sample UCs
                  </summary>
                  <ul className="mt-1 space-y-1">
                    {fam.tags.flatMap((t) =>
                      t.examples.slice(0, 1).map((e) => (
                        <li key={e.use_case_id} className="text-zen-dark-teal">
                          <span className="font-mono text-[9px] text-zen-dark-teal/60 mr-1">
                            {e.use_case_id}
                          </span>
                          <Link to={`/subcap?id=${encodeURIComponent(e.sub_cap_id)}`} className="hover:text-zen-dark-green">
                            {e.description?.slice(0, 80)}
                          </Link>
                        </li>
                      )),
                    )}
                  </ul>
                </details>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
