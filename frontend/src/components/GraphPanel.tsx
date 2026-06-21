"use client";

import { useEffect, useMemo, useState } from "react";
import { fetchGraph } from "@/api/client";
import type { GraphResponse } from "@/types";

const TYPES = ["keyword", "author", "topic"] as const;
const SIZE = 360;
const RADIUS = 150;

export function GraphPanel() {
  const [type, setType] = useState<(typeof TYPES)[number]>("keyword");
  const [data, setData] = useState<GraphResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setData(null);
    setError(null);
    fetchGraph(type)
      .then((response) => {
        if (active) {
          setData(response);
        }
      })
      .catch((graphError: unknown) => {
        if (active) {
          setError(graphError instanceof Error ? graphError.message : "Failed to load graph");
        }
      });
    return () => {
      active = false;
    };
  }, [type]);

  const layout = useMemo(() => {
    if (!data) {
      return { positions: new Map<string, { x: number; y: number }>(), nodes: [], edges: [] };
    }
    const nodes = data.nodes.slice(0, 60);
    const positions = new Map<string, { x: number; y: number }>();
    nodes.forEach((node, index) => {
      const angle = (2 * Math.PI * index) / nodes.length;
      positions.set(node.id, {
        x: SIZE / 2 + RADIUS * Math.cos(angle),
        y: SIZE / 2 + RADIUS * Math.sin(angle)
      });
    });
    const edges = data.edges.filter((edge) => positions.has(edge.source) && positions.has(edge.target)).slice(0, 200);
    return { positions, nodes, edges };
  }, [data]);

  return (
    <section className="border border-line bg-panel/90 p-4 sm:p-5">
      <div className="flex items-center justify-between border-b border-line pb-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-cyanSoft">Knowledge Graph</p>
          <h2 className="mt-2 text-base font-semibold text-silver">Co-occurrence & collaboration</h2>
        </div>
        <div className="flex gap-1">
          {TYPES.map((option) => (
            <button
              className={`border px-2 py-1 text-[11px] uppercase tracking-wide ${
                option === type ? "border-cyanSoft/60 bg-cyanSoft/10 text-cyanSoft" : "border-line text-silver/55"
              }`}
              key={option}
              onClick={() => setType(option)}
              type="button"
            >
              {option}
            </button>
          ))}
        </div>
      </div>

      {error ? (
        <p className="mt-4 border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">{error}</p>
      ) : null}

      {data ? (
        <div className="mt-4 flex flex-col items-center">
          <svg height={SIZE} role="img" viewBox={`0 0 ${SIZE} ${SIZE}`} width="100%">
            {layout.edges.map((edge, index) => {
              const a = layout.positions.get(edge.source);
              const b = layout.positions.get(edge.target);
              if (!a || !b) {
                return null;
              }
              return <line key={index} stroke="#3a4250" strokeWidth={0.6} x1={a.x} x2={b.x} y1={a.y} y2={b.y} />;
            })}
            {layout.nodes.map((node) => {
              const point = layout.positions.get(node.id);
              if (!point) {
                return null;
              }
              return (
                <g key={node.id}>
                  <circle cx={point.x} cy={point.y} fill="#4fd1c5" r={3} />
                  <title>{node.label ?? node.id}</title>
                </g>
              );
            })}
          </svg>
          <p className="mt-2 text-[11px] text-silver/45">
            {data.nodes.length} nodes · {data.edges.length} edges (showing up to 60)
          </p>
        </div>
      ) : null}
    </section>
  );
}
