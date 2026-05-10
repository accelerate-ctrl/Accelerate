import { Construction } from 'lucide-react';

export default function PageStub({ title, batch, summary }: { title: string; batch: number; summary?: string }) {
  return (
    <div className="max-w-3xl mx-auto mt-8 bg-white rounded-lg shadow-sm border border-zen-light-green/40 p-6">
      <div className="flex items-center gap-3 mb-3">
        <div className="p-2 bg-zen-light-green/40 rounded text-zen-dark-teal">
          <Construction size={18} />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-zen-dark-green">{title}</h1>
          <div className="text-xs text-zen-dark-teal/70">activates in Batch {batch}</div>
        </div>
      </div>
      {summary && <p className="text-sm text-zen-dark-teal mt-2 leading-relaxed">{summary}</p>}
      <div className="mt-4 text-xs text-zen-dark-teal/60">
        Batch 0 ships the shell only — every page route exists and is reachable. Functional content lights up batch
        by batch (see README and ARCHITECTURE.md for the roadmap).
      </div>
    </div>
  );
}
