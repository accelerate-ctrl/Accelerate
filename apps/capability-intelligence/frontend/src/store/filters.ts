// Global filter context that propagates across pages.
import { create } from 'zustand';

type FilterState = {
  pillarId: string | null;
  categoryId: string | null;
  search: string;
  setPillar: (pid: string | null) => void;
  setCategory: (cid: string | null) => void;
  setSearch: (q: string) => void;
  reset: () => void;
};

export const useFilters = create<FilterState>((set) => ({
  pillarId: null,
  categoryId: null,
  search: '',
  setPillar: (pillarId) => set({ pillarId }),
  setCategory: (categoryId) => set({ categoryId }),
  setSearch: (search) => set({ search }),
  reset: () => set({ pillarId: null, categoryId: null, search: '' }),
}));
