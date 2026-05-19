import { useCallback, useRef, useState } from 'react';
import { CheckCircle2, Upload, AlertTriangle, Loader2 } from 'lucide-react';
import { apiPostForm, type CatalogueStatePillar, type IngestRun } from '@/lib/api';

type Props = {
  pillar: CatalogueStatePillar;
  onUploaded: (result: IngestRun) => void;
};

const PILLAR_NAMES: Record<string, string> = {
  P1: 'Strategy, Governance & Culture',
  P2: 'Customer Experience & Engagement',
  P3: 'Process Automation & Operations',
  P4: 'Data & AI Enablement',
};

export default function PillarUploadDropZone({ pillar, onUploaded }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hover, setHover] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    async (file: File) => {
      if (!file.name.toLowerCase().match(/\.(xlsx|xlsm)$/)) {
        setError('File must be .xlsx or .xlsm');
        return;
      }
      setBusy(true);
      setError(null);
      try {
        const form = new FormData();
        form.append('pillar_id', pillar.pillar_id);
        form.append('file', file);
        const result = await apiPostForm<IngestRun>('/sheets/upload', form);
        onUploaded(result);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : 'Upload failed');
      } finally {
        setBusy(false);
      }
    },
    [pillar.pillar_id, onUploaded],
  );

  const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setHover(false);
    const file = e.dataTransfer.files?.[0];
    if (file) void handleFile(file);
  };

  const status = pillar.schema_status;
  const statusColor =
    status === 'complete' ? 'text-zen-teal'
    : status === 'incomplete' ? 'text-zen-orange'
    : 'text-zen-muted-text';
  const StatusIcon =
    status === 'complete' ? CheckCircle2
    : status === 'incomplete' ? AlertTriangle
    : Upload;

  const subcaps = pillar.row_counts?.subcaps;
  const stories = pillar.row_counts?.stories;
  const ingested = pillar.ingested_at
    ? new Date(pillar.ingested_at).toLocaleString()
    : null;

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setHover(true); }}
      onDragLeave={() => setHover(false)}
      onDrop={onDrop}
      className={`rounded-lg border-2 border-dashed p-3 transition-colors ${
        hover
          ? 'border-zen-teal bg-zen-light-green/30'
          : 'border-zen-separator bg-white hover:border-zen-light-teal'
      }`}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <div>
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-semibold text-zen-dark-green">
              {pillar.pillar_id}
            </span>
            <span className={`inline-flex items-center gap-0.5 text-[10px] uppercase tracking-wider ${statusColor}`}>
              <StatusIcon size={10} />
              {status}
            </span>
          </div>
          <div className="text-xs text-zen-dark-teal/70">
            {PILLAR_NAMES[pillar.pillar_id] || pillar.name}
          </div>
        </div>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={busy}
          className="text-xs px-2 py-1 rounded bg-zen-teal text-white hover:bg-zen-dark-teal disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center gap-1"
        >
          {busy ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
          {busy ? 'Parsing…' : 'Upload .xlsx'}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".xlsx,.xlsm"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void handleFile(f);
            e.target.value = '';
          }}
        />
      </div>

      <div className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-[11px] text-zen-dark-teal/80">
        <span className="text-zen-muted-text">Subcaps</span>
        <span className="text-right font-mono">{subcaps ?? '—'}</span>
        <span className="text-zen-muted-text">Stories</span>
        <span className="text-right font-mono">{stories ?? '—'}</span>
        <span className="text-zen-muted-text">File</span>
        <span className="text-right truncate" title={pillar.source_file_name || ''}>
          {pillar.source_file_name || 'none'}
        </span>
        <span className="text-zen-muted-text">Loaded</span>
        <span className="text-right">{ingested || '—'}</span>
      </div>

      {error && (
        <div className="mt-2 text-[11px] text-zen-orange bg-zen-light-orange/40 rounded px-2 py-1 inline-flex items-start gap-1">
          <AlertTriangle size={11} className="mt-0.5 shrink-0" />
          <span className="break-words">{error}</span>
        </div>
      )}
      {!busy && !error && (
        <div className="mt-2 text-[10px] text-zen-muted-text">
          Drop .xlsx here or click Upload.
        </div>
      )}
    </div>
  );
}
