import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import CatalogueSunburst from '../src/components/CatalogueSunburst';
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

describe('CatalogueSunburst', () => {
  it('renders an svg with arc paths', () => {
    const { container } = render(
      <MemoryRouter>
        <CatalogueSunburst tree={tree} size={200} />
      </MemoryRouter>,
    );
    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
    const paths = container.querySelectorAll('path');
    expect(paths.length).toBeGreaterThan(0);
  });

  it('shows empty state when tree has no pillars', () => {
    const { container, getByText } = render(
      <MemoryRouter>
        <CatalogueSunburst tree={{ pillars: [] }} size={200} />
      </MemoryRouter>,
    );
    expect(container.querySelector('svg')).toBeNull();
    expect(getByText(/No catalogue data yet/)).toBeInTheDocument();
  });
});
