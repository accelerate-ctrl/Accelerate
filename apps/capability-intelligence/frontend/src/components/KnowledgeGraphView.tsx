import { useEffect, useRef } from 'react';
import cytoscape, { type Core, type ElementDefinition } from 'cytoscape';
// @ts-expect-error — no types shipped with cose-bilkent
import coseBilkent from 'cytoscape-cose-bilkent';
import type { GraphElements } from '@/lib/api';

let registered = false;
function ensureRegistered() {
  if (!registered) {
    cytoscape.use(coseBilkent);
    registered = true;
  }
}

const KIND_COLOR: Record<string, string> = {
  Pillar: '#1c4a4d',
  Category: '#185f60',
  L1_Capability: '#27bbaf',
  Subcap: '#62d7b8',
  L3_Platform: '#fe9732',
  L4_Feature: '#ffcb99',
  UseCase: '#b0eed3',
  UC_Tag: '#e8f7f6',
  Theme: '#185f60',
  MaturityDescriptor: '#62d7b8',
  Subvertical: '#1c4a4d',
  Cluster: '#fe9732',
  VC_Stage: '#27bbaf',
  Persona: '#b0eed3',
};

export default function KnowledgeGraphView({ elements, height = 560, onSelect }: { elements: GraphElements; height?: number; onSelect?: (nodeId: string) => void }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);

  useEffect(() => {
    ensureRegistered();
    if (!ref.current) return;
    const els: ElementDefinition[] = [
      ...elements.nodes.map((n) => ({ data: n.data })),
      ...elements.edges.map((e) => ({ data: e.data })),
    ];
    const cy = cytoscape({
      container: ref.current,
      elements: els,
      style: [
        {
          selector: 'node',
          style: {
            label: 'data(label)',
            'background-color': (n: cytoscape.NodeSingular) => KIND_COLOR[n.data('kind') as string] || '#62d7b8',
            color: '#1c4a4d',
            'font-size': 8,
            'text-wrap': 'wrap',
            'text-max-width': '90px',
            'text-valign': 'bottom',
            'text-margin-y': 3,
            width: 14,
            height: 14,
            'border-width': 1,
            'border-color': '#fff',
          } as cytoscape.Css.Node,
        },
        {
          selector: 'edge',
          style: {
            'curve-style': 'bezier',
            'line-color': '#cfeae4',
            width: 1,
            'target-arrow-color': '#cfeae4',
            'target-arrow-shape': 'triangle',
            'arrow-scale': 0.6,
          } as cytoscape.Css.Edge,
        },
        {
          selector: 'node:selected',
          style: { 'border-width': 3, 'border-color': '#fe9732' } as cytoscape.Css.Node,
        },
      ],
      layout: { name: 'cose-bilkent', animate: false, idealEdgeLength: 60, nodeRepulsion: 4500 } as unknown as cytoscape.LayoutOptions,
      wheelSensitivity: 0.2,
    });
    cyRef.current = cy;

    if (onSelect) {
      cy.on('tap', 'node', (evt) => onSelect(evt.target.id()));
    }

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [elements, onSelect]);

  return <div ref={ref} style={{ width: '100%', height }} className="bg-white rounded border border-zen-light-green/40" />;
}
