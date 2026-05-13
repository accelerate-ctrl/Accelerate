// Global filter context that propagates across pages.
import { create } from 'zustand';

// Canonical subverticals from ZDS skill — referenced as L4 grouping across
// every page. Kept inline (no API call) because the list is small + static.
export const SUBVERTICALS = [
  { code: 'fs-retail-banking',    label: 'Retail Banking' },
  { code: 'fs-commercial-banking', label: 'Commercial Banking' },
  { code: 'fs-credit-unions',     label: 'Credit Unions' },
  { code: 'fs-wealth-asset-mgmt', label: 'Wealth & Asset Mgmt' },
  { code: 'fs-wealth-rias',       label: 'Wealth — RIAs' },
  { code: 'fs-insurance-carriers',label: 'Insurance Carriers' },
  { code: 'fs-insurance-brokers', label: 'Insurance Brokerages' },
  { code: 'fs-farm-credit',       label: 'Farm Credit' },
  { code: 'fs-cib-banking',       label: 'CIB Banking' },
] as const;

type FilterState = {
  pillarId: string | null;
  categoryId: string | null;
  subverticalCode: string | null;
  search: string;
  setPillar: (pid: string | null) => void;
  setCategory: (cid: string | null) => void;
  setSubvertical: (code: string | null) => void;
  setSearch: (q: string) => void;
  reset: () => void;
};

export const useFilters = create<FilterState>((set) => ({
  pillarId: null,
  categoryId: null,
  subverticalCode: null,
  search: '',
  setPillar: (pillarId) => set({ pillarId }),
  setCategory: (categoryId) => set({ categoryId }),
  setSubvertical: (subverticalCode) => set({ subverticalCode }),
  setSearch: (search) => set({ search }),
  reset: () => set({ pillarId: null, categoryId: null, subverticalCode: null, search: '' }),
}));
