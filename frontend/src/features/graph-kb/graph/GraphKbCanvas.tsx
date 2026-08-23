/** G6 canvas that renders only a graph-view subgraph (never a full entity dump). */

import { Empty, Spin } from 'antd'
import { Graph, NodeEvent } from '@antv/g6'
import type { EdgeData, GraphData, IElementEvent, NodeData } from '@antv/g6'
import { useEffect, useMemo, useRef } from 'react'
import './GraphKbCanvas.css'

type GraphKbCanvasProps = {
  /** graph-view nodes; canvas never receives a full entity list. */
  nodes: Record<string, unknown>[]
  /** graph-view edges matching those nodes. */
  edges: Record<string, unknown>[]
  /** Engine / projection id to highlight as the current seed. */
  seedId?: string
  /** True while a subgraph request is in flight. */
  loading?: boolean
  /** Hint when no subgraph is loaded yet (not the empty-projection state). */
  emptyHint: string
  /** Node click: parent must re-request graph-view with hops=2 for this seed. */
  onNodeClick: (nodeId: string) => void
}

/** Read a string field from a loose graph-view record. */
function asString(record: Record<string, unknown>, key: string): string {
  const value = record[key]
  if (typeof value === 'string') return value
  if (value == null) return ''
  return String(value)
}

/** Map one graph-view node onto G6 NodeData (id + label only). */
function toG6Node(record: Record<string, unknown>, seedId?: string): NodeData | null {
  const id = asString(record, 'id')
  if (!id) return null
  const label = asString(record, 'name') || id
  return {
    id,
    data: {
      label,
      entityType: asString(record, 'entity_type'),
      description: asString(record, 'description'),
      seed: seedId != null && (id === seedId || asString(record, 'projection_id') === seedId),
    },
  }
}

/** Map one graph-view edge onto G6 EdgeData (source/target from from_id/to_id). */
function toG6Edge(record: Record<string, unknown>, index: number): EdgeData | null {
  const source = asString(record, 'from_id')
  const target = asString(record, 'to_id')
  if (!source || !target) return null
  return {
    id: `e-${source}-${target}-${index}`,
    source,
    target,
    data: { label: asString(record, 'type') },
  }
}

/** Convert a graph-view payload into G6 GraphData. */
export function graphViewToG6Data(
  nodes: Record<string, unknown>[],
  edges: Record<string, unknown>[],
  seedId?: string,
): GraphData {
  const g6Nodes = nodes.map((row) => toG6Node(row, seedId)).filter((row): row is NodeData => row != null)
  const ids = new Set(g6Nodes.map((row) => String(row.id)))
  const g6Edges = edges
    .map((row, index) => toG6Edge(row, index))
    .filter((row): row is EdgeData => row != null && ids.has(String(row.source)) && ids.has(String(row.target)))
  return { nodes: g6Nodes, edges: g6Edges }
}

/** Read theme tokens from the canvas host for G6 paints. */
function readCanvasColors(el: HTMLElement): {
  ink: string
  primary: string
  seed: string
  edge: string
} {
  const styles = getComputedStyle(el)
  return {
    ink: styles.getPropertyValue('--minerva-ink').trim() || '#e8f0f8',
    primary: styles.getPropertyValue('--minerva-primary').trim() || '#38bdf8',
    seed: styles.getPropertyValue('--minerva-warning').trim() || '#f59e0b',
    edge: styles.getPropertyValue('--minerva-ink-muted').trim() || '#94a3b8',
  }
}

/** Subgraph canvas: height 100%, 4px radius; node click asks parent for hops=2. */
export function GraphKbCanvas({
  nodes,
  edges,
  seedId,
  loading = false,
  emptyHint,
  onNodeClick,
}: GraphKbCanvasProps) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const graphRef = useRef<Graph | null>(null)
  const onNodeClickRef = useRef(onNodeClick)
  onNodeClickRef.current = onNodeClick

  const data = useMemo(() => graphViewToG6Data(nodes, edges, seedId), [edges, nodes, seedId])
  const hasSubgraph = (data.nodes?.length ?? 0) > 0

  useEffect(() => {
    const host = hostRef.current
    if (!host || !hasSubgraph) {
      graphRef.current?.destroy()
      graphRef.current = null
      return
    }

    const colors = readCanvasColors(host)
    const applySize = (graph: Graph) => {
      const rect = host.getBoundingClientRect()
      const width = Math.max(8, Math.floor(rect.width))
      const height = Math.max(8, Math.floor(rect.height))
      graph.setSize(width, height)
    }

    const graph = new Graph({
      container: host,
      data,
      autoFit: 'view',
      padding: 24,
      animation: false,
      layout: {
        type: 'force',
        preventOverlap: true,
      },
      behaviors: ['drag-canvas', 'zoom-canvas', 'drag-element'],
      node: {
        style: {
          size: (datum) => (datum.data && datum.data['seed'] ? 36 : 24),
          fill: (datum) => (datum.data && datum.data['seed'] ? colors.seed : colors.primary),
          stroke: colors.ink,
          lineWidth: 1,
          labelText: (datum) => String(datum.data?.['label'] ?? datum.id),
          labelFill: colors.ink,
          labelFontSize: 11,
          labelPlacement: 'bottom',
        },
      },
      edge: {
        style: {
          stroke: colors.edge,
          lineWidth: 1,
          endArrow: true,
          labelText: (datum) => String(datum.data?.['label'] ?? ''),
          labelFill: colors.edge,
          labelFontSize: 10,
        },
      },
    })
    graph.on(NodeEvent.CLICK, (event: IElementEvent) => {
      const id = event.target?.id
      if (id) onNodeClickRef.current(String(id))
    })
    applySize(graph)
    void graph.render()
    graphRef.current = graph

    const ro = new ResizeObserver(() => {
      if (!graphRef.current) return
      applySize(graphRef.current)
    })
    ro.observe(host)

    return () => {
      ro.disconnect()
      graph.destroy()
      if (graphRef.current === graph) graphRef.current = null
    }
  }, [data, hasSubgraph])

  return (
    <div className="minerva-graph-kb-canvas">
      <Spin spinning={loading} className="minerva-graph-kb-canvas__spin">
        <div ref={hostRef} className="minerva-graph-kb-canvas__host" />
        {!hasSubgraph && !loading ? (
          <div className="minerva-graph-kb-canvas__empty">
            <Empty description={emptyHint} image={Empty.PRESENTED_IMAGE_SIMPLE} />
          </div>
        ) : null}
      </Spin>
    </div>
  )
}
