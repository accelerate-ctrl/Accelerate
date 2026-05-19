import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  BookOpenCheck,
  History,
  Sparkles,
  X,
} from 'lucide-react';
import { apiGet, type Overview } from '@/lib/api';
import PillarBreakdown, { type Structure } from '@/components/PillarBreakdown';
import PillarRefreshPanel from '@/components/PillarRefreshPanel';
import QaHealthTile from '@/components/QaHealthTile';
import horizonBand from '@/assets/illustrations/horizon_minimal_band.jpg';

export default function MissionControl() {
  const { data: overview, isLoading, error } = useQuery<Overview>({
    queryKey: ['overview'],
    queryFn: () => apiGet<Overview>('/catalogue/overview'),
  });

  const { data: structure } = useQuery<Structure>({
    queryKey: ['catalogue-structure'],
    queryFn: () => apiGet<Structure>('/catalogue/structure'),
  });

  const totals = structure?.totals;

  return (
    <div className="space-y-4 md:space-y-6">
      {/* Title row */}
      <div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">Mission Control</h1>
        <p className="text-sm text-zen-dark-teal/80 max-w-3xl">
          The four-pillar capability catalogue at a glance: every pillar shows its categories,
          L1 capabilities, and subcaps. Click any pillar to expand it; click an L1 to drill
          into its subcaps.
        </p>
      </div>

      {isLoading && <div className="text-xs text-zen-muted-text">Loading…</div>}

      {error && (
        <div className="text-xs text-zen-orange bg-zen-light-orange/40 border border-zen-orange/30 rounded p-3">
          Failed to load overview: {error instanceof Error ? error.message : 'unknown error'}.
          If this is a fresh deploy, click <b>Pull sources</b> (top-right) once to ingest from
          Drive; this page populates after the catalogue ingest finishes.
        </div>
      )}

      {overview && overview.totals.pillars_loaded === 0 && (
        <div className="relative overflow-hidden rounded-lg border border-zen-separator bg-white shadow-sm">
          <img
            src={horizonBand}
            alt=""
            aria-hidden
            className="absolute inset-0 w-full h-full object-cover opacity-25"
          />
          <div className="relative p-6 max-w-xl">
            <div className="text-[11px] uppercase tracking-wider text-zen-teal font-semibold mb-1">
              Get started
            </div>
            <h2 className="text-lg font-semibold text-zen-dark-green mb-1">
              No catalogue ingested yet
            </h2>
            <p className="text-sm text-zen-text-gray">
              Click <b>Pull sources</b> (top-right) to fetch Pillar 1–4 workbooks from the
              configured Drive folder. The ingestor auto-picks the highest{' '}
              <code className="text-xs">vX.Y</code> version per pillar; files containing{' '}
              <code className="text-xs">inactive</code> are skipped.
            </p>
          </div>
        </div>
      )}

      {/* IMP-14 — catalogue changelog tile. Shows when a new catalogue
          version was ingested in the last 7 days and surfaces the run
          metadata + a link to the version timeline. Dismissible per
          run_id via localStorage so users only see each update once. */}
      {overview?.last_ingest && (
        <CatalogueChangelogTile lastIngest={overview.last_ingest} />
      )}

      {/* Top KPI strip — four compact tiles on desktop, two-column on small */}
      {totals && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 md:gap-3">
          <KPI label="Pillars" value={totals.pillars} sub={overview ? `${overview.totals.pillars_loaded}/4 loaded` : ''} />
          <KPI label="Categories" value={totals.categories} />
          <KPI label="L1 capabilities" value={totals.l1s} />
          <KPI label="Subcaps" value={totals.subcaps} accent />
        </div>
      )}

      {/* Main pillar breakdown — the new declutterred hierarchy view */}
      {structure && totals && totals.pillars > 0 && (
        <PillarBreakdown data={structure} />
      )}

      {/* Sidebar — last-ingest + quick actions. Folded to a single row on
          mobile, full sidebar on lg+ */}
      {overview && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <div className="bg-white rounded-lg border border-zen-separator p-3 lg:col-span-1">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-zen-dark-green flex items-center gap-1.5 mb-2">
              <History size={13} /> Last ingest
            </h2>
            {overview.last_ingest ? (
              <div className="text-xs text-zen-text-gray space-y-0.5">
                <div className="font-mono text-[10px] text-zen-muted-text truncate">
                  {overview.last_ingest.run_id}
                </div>
                <div>started: {new Date(overview.last_ingest.started_at).toLocaleString()}</div>
                <div>loaded: {overview.last_ingest.pillars_loaded.join(', ') || '—'}</div>
              </div>
            ) : (
              <div className="text-xs text-zen-muted-text italic">
                No ingestions yet. Click <b>Pull sources</b> (top-right) to fetch from Drive.
              </div>
            )}
          </div>

          <div className="lg:col-span-2">
            <PillarRefreshPanel />
          </div>
        </div>
      )}

      {/* Quick actions — concise grid */}
      {overview && totals && totals.subcaps > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
          <QuickLink to="/explorer" icon={<BookOpenCheck size={14} />} label="Capability Explorer" />
          <QuickLink to="/graph" icon={<History size={14} />} label="Knowledge Graph" />
          <QuickLink to="/flags" icon={<AlertTriangle size={14} />} label="Review flags" warn />
          <QuickLink to="/suggestions" icon={<BookOpenCheck size={14} />} label="AI Suggestions" />
        </div>
      )}

      {/* Phase 5 — QA & Audit roll-up surfaced on Mission Control so
          engineers see budget / source-health / retrieval at a glance. */}
      <QaHealthTile />
    </div>
  );
}

function KPI({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: number;
  sub?: string;
  accent?: boolean;
}) {
  return (
    <div className="bg-white rounded-lg border border-zen-separator p-3 md:p-4">
      <div className="text-[10px] uppercase tracking-wider text-zen-muted-text">{label}</div>
      <div
        className={`text-xl md:text-2xl font-semibold mt-0.5 ${
          accent ? 'text-zen-teal' : 'text-zen-dark-green'
        }`}
      >
        {value.toLocaleString()}
      </div>
      {sub && <div className="text-[10px] text-zen-muted-text mt-0.5">{sub}</div>}
    </div>
  );
}

function QuickLink({
  to,
  icon,
  label,
  warn,
}: {
  to: string;
  icon: React.ReactNode;
  label: string;
  warn?: boolean;
}) {
  return (
    <Link
      to={to}
      className={`flex items-center gap-2 text-xs px-2.5 py-2 rounded border transition-colors ${
        warn
          ? 'bg-zen-light-orange/30 border-zen-orange/30 text-zen-dark-green hover:bg-zen-light-orange/50'
          : 'bg-white border-zen-separator text-zen-dark-green hover:bg-zen-ice'
      }`}
    >
      <span className="text-zen-teal">{icon}</span>
      <span className="truncate">{label}</span>
    </Link>
  );
}


/**
 * IMP-14 — catalogue changelog tile.
 *
 * Renders a dismissible notice when the most recent ingest is within
 * the last 7 days. The dismissal is keyed on the specific run_id so
 * future ingests will re-surface a fresh tile. Falls back gracefully
 * when started_at is missing or unparseable.
 */
function CatalogueChangelogTile({
  lastIngest,
}: {
  lastIngest: NonNullable<Overview['last_ingest']>;
}) {
  const storageKey = `mc-changelog-dismissed:${lastIngest.run_id}`;
  const [dismissed, setDismissed] = useState(() => {
    try {
      return window.localStorage.getItem(storageKey) === '1';
    } catch {
      return false;
    }
  });

  // 7-day visibility window per IMP-14 spec.
  const started = new Date(lastIngest.started_at);
  if (Number.isNaN(started.getTime())) return null;
  const ageDays = (Date.now() - started.getTime()) / 86400000;
  if (ageDays > 7) return null;
  if (dismissed) return null;

  const pillars = lastIngest.pillars_loaded?.join(', ') || '—';
  const relative = ageDays < 1
    ? 'today'
    : ageDays < 2
    ? 'yesterday'
    : `${Math.floor(ageDays)} days ago`;

  return (
    <div
      role="status"
      aria-live="polite"
      className="bg-surface-overlay border border-zen-teal/40 rounded-lg p-3 flex items-start gap-2"
    >
      <Sparkles size={16} className="text-zen-teal shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-fg">Catalogue updated {relative}</div>
        <div className="text-xs text-fg-soft mt-0.5">
          Pillars loaded: {pillars} ·{' '}
          <span className="font-mono">{lastIngest.run_id}</span>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
          <Link
            to="/versions"
            className="text-zen-teal hover:text-zen-dark-teal underline"
          >
            View version timeline
          </Link>
          <span className="text-fg-muted">·</span>
          <Link
            to="/diff"
            className="text-zen-teal hover:text-zen-dark-teal underline"
          >
            Open diff viewer
          </Link>
        </div>
      </div>
      <button
        type="button"
        aria-label="dismiss catalogue update"
        onClick={() => {
          try {
            window.localStorage.setItem(storageKey, '1');
          } catch {
            /* ignore storage failures */
          }
          setDismissed(true);
        }}
        className="text-fg-soft hover:text-fg shrink-0"
      >
        <X size={14} />
      </button>
    </div>
  );
}
