type Label = 'FACT' | 'INFERENCE' | 'HYPOTHESIS' | 'CEILING_ESTIMATE';

const styles: Record<Label, string> = {
  FACT: 'bg-claim-fact text-white',
  INFERENCE: 'bg-claim-inference text-white',
  HYPOTHESIS: 'bg-claim-hypothesis text-zen-dark-green',
  CEILING_ESTIMATE: 'bg-claim-ceiling text-white',
};

export default function ClaimLabelBadge({ label }: { label: Label }) {
  return (
    <span
      className={`text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded ${styles[label]}`}
    >
      {label.replace('_', ' ')}
    </span>
  );
}
