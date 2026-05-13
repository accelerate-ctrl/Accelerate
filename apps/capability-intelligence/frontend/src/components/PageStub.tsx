import { Construction } from 'lucide-react';

export default function PageStub({ title, batch, summary }: { title: string; batch: number; summary?: string }) {
  return (
    <div className="max-w-3xl mx-auto mt-6 bg-white rounded-lg shadow-sm border border-zen-separator p-6">
      <div className="flex items-center gap-3 mb-2">
        <div className="p-2 bg-zen-ice rounded text-zen-dark-teal">
          <Construction size={18} />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-zen-dark-green">{title}</h1>
          <div className="text-[11px] uppercase tracking-wider text-zen-muted-text">Coming soon</div>
        </div>
      </div>
      {summary && <p className="text-sm text-zen-text-gray mt-2 leading-relaxed">{summary}</p>}
      <div className="mt-3 text-xs text-zen-muted-text" data-batch={batch}>
        This view is part of the roadmap. Use <b>Pull sources</b> in the header to populate
        the data layer; the panels that already ship — Mission Control, Capability Explorer,
        SOW Library, Story Library, News Watch — render real data immediately after.
      </div>
    </div>
  );
}
