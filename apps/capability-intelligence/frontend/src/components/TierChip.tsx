type Tier = 'T1' | 'T2' | 'T3' | 'T4' | 'T5';

const styles: Record<Tier, string> = {
  T1: 'bg-tier-t1 text-white',
  T2: 'bg-tier-t2 text-white',
  T3: 'bg-tier-t3 text-zen-dark-green',
  T4: 'bg-tier-t4 text-zen-dark-green',
  T5: 'bg-tier-t5 text-white',
};

export default function TierChip({ tier }: { tier: Tier }) {
  return (
    <span className={`text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded ${styles[tier]}`}>
      {tier}
    </span>
  );
}
