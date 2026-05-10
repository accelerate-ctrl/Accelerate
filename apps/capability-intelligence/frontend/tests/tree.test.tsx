import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import CatalogueTree from '../src/components/CatalogueTree';
import type { Tree } from '../src/lib/api';

const tree: Tree = {
  pillars: [
    {
      pillar_id: 'P1',
      name: 'Strategic Foundation',
      categories: [
        {
          category_id: 'P1C1',
          name: 'P1C1',
          l1: [
            {
              name: 'Strategy Foundation & Alignment',
              subcaps: [
                { sub_cap_id: 'P1C1.1.1', sub_cap_name: 'Digital Strategy Document' },
                { sub_cap_id: 'P1C1.1.2', sub_cap_name: 'Business Alignment' },
              ],
            },
          ],
        },
      ],
    },
  ],
};

describe('CatalogueTree', () => {
  it('renders pillar headers and expands on click', () => {
    render(
      <MemoryRouter>
        <CatalogueTree tree={tree} search="" />
      </MemoryRouter>,
    );
    const pillarBtn = screen.getByText('Strategic Foundation');
    expect(pillarBtn).toBeInTheDocument();
    fireEvent.click(pillarBtn);
    expect(screen.getByText('P1C1')).toBeInTheDocument();
  });

  it('filters by search across all subcaps', () => {
    render(
      <MemoryRouter>
        <CatalogueTree tree={tree} search="Business" />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText('Strategic Foundation'));
    fireEvent.click(screen.getByText('P1C1'));
    expect(screen.getByText('Business Alignment')).toBeInTheDocument();
    expect(screen.queryByText('Digital Strategy Document')).toBeNull();
  });
});
