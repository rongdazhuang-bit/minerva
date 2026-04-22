import { addRuleVersion, getRule, publishVersion } from '@/api/rules'
import { ApiError } from '@/api/client'
import { useAuth } from '@/app/AuthContext'
import {
  addEdge,
  Background,
  BackgroundVariant,
  Controls,
  type Connection,
  type Edge,
  type Node,
  type NodeTypes,
  Handle,
  MiniMap,
  type NodeProps,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Breadcrumb, Button, Select, message } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'

import './RuleEditorPage.css'

function accentClass(nodeType: string): string {
  if (['start', 'end', 'branch', 'noop'].includes(nodeType)) {
    return `rule-node__accent--${nodeType}`
  }
  return 'rule-node__accent--default'
}

function MinervaNode(p: NodeProps) {
  const { t } = useTranslation()
  const data = p.data as { nodeType: string; label: string }
  const nodeType = data.nodeType
  const typeKey = `designer.nodeType.${nodeType}` as const
  const typeLabel = t(typeKey) !== typeKey ? t(typeKey) : nodeType
  return (
    <div className="rule-node">
      <div className={`rule-node__accent ${accentClass(nodeType)}`} />
      <div className="rule-node__head">
        <span className="rule-node__type">{typeLabel}</span>
      </div>
      <div className="rule-node__body">{data.label || typeLabel}</div>
      <Handle
        className="rule-node__handle rule-node__handle--target"
        type="target"
        position={Position.Top}
      />
      <Handle
        className="rule-node__handle rule-node__handle--source"
        type="source"
        position={Position.Bottom}
      />
    </div>
  )
}

const defaultEdgeOptions = { type: 'smoothstep' as const }

function flowToNodesEdges(flow: Record<string, unknown> | null | undefined): {
  nodes: Node[]
  edges: Edge[]
} {
  if (!flow || typeof flow !== 'object') {
    return {
      nodes: [
        { id: 'a', type: 'minerva', position: { x: 0, y: 0 }, data: { nodeType: 'start', label: 'start' } },
        { id: 'b', type: 'minerva', position: { x: 200, y: 0 }, data: { nodeType: 'end', label: 'end' } },
      ],
      edges: [
        { id: 'e1', source: 'a', target: 'b', type: 'smoothstep' },
      ],
    }
  }
  const rawNodes = (flow.nodes as { id: string; type: string; data?: Record<string, unknown> }[]) ?? []
  const rawEdges = (flow.edges as { id: string; source: string; target: string }[]) ?? []
  const nodes: Node[] = rawNodes.map((n, i) => ({
    id: n.id,
    type: 'minerva',
    position: { x: 40 + (i % 4) * 200, y: 40 + Math.floor(i / 4) * 120 },
    data: { nodeType: n.type, label: n.type, rawData: n.data },
  }))
  const edges: Edge[] = rawEdges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    type: 'smoothstep',
  }))
  return { nodes, edges }
}

function buildFlowJson(nodes: Node[], edges: Edge[]): Record<string, unknown> {
  return {
    schema_version: 1,
    nodes: nodes.map((n) => {
      const d = n.data as { nodeType: string; rawData?: Record<string, unknown> }
      return {
        id: n.id,
        type: d.nodeType,
        data: d.rawData ?? {},
      }
    }),
    edges: edges.map((e) => ({ id: e.id, source: e.source, target: e.target })),
  }
}

export function RuleEditorPage() {
  const { ruleId = '' } = useParams()
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const [title, setTitle] = useState('')
  const [latest, setLatest] = useState<{ id: string; state: string } | null>(null)
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])

  const addTypeOptions = useMemo(
    () => [
      { value: 'start', label: t('designer.nodeType.start') },
      { value: 'end', label: t('designer.nodeType.end') },
      { value: 'branch', label: t('designer.nodeType.branch') },
      { value: 'noop', label: t('designer.nodeType.noop') },
    ],
    [t],
  )

  const nodeTypes: NodeTypes = useMemo(
    () => ({
      minerva: MinervaNode,
    }),
    [],
  )

  const load = useCallback(async () => {
    if (!workspaceId || !ruleId) return
    try {
      const d = await getRule(workspaceId, ruleId)
      setTitle(d.name)
      if (d.latest_version) {
        setLatest({ id: d.latest_version.id, state: d.latest_version.state })
        const g = flowToNodesEdges(d.latest_version.flow_json)
        setNodes(g.nodes)
        setEdges(g.edges)
      } else {
        setLatest(null)
        const g = flowToNodesEdges(null)
        setNodes(g.nodes)
        setEdges(g.edges)
      }
    } catch (e) {
      if (e instanceof ApiError) void message.error(e.message)
    }
  }, [ruleId, setEdges, setNodes, workspaceId])

  useEffect(() => {
    void load()
  }, [load])

  const onConnect = useCallback(
    (c: Connection) =>
      setEdges((e) => addEdge({ id: `e-${crypto.randomUUID()}`, type: 'smoothstep', ...c }, e)),
    [setEdges],
  )

  const addNode = (nodeType: string) => {
    const id = crypto.randomUUID()
    setNodes((ns) => [
      ...ns,
      {
        id,
        type: 'minerva',
        position: { x: 80 + Math.random() * 200, y: 80 + Math.random() * 200 },
        data: { nodeType, label: nodeType, rawData: {} },
      },
    ])
  }

  const save = () => {
    if (!workspaceId) return
    const flow = buildFlowJson(nodes, edges)
    void (async () => {
      try {
        const v = await addRuleVersion(workspaceId, ruleId, flow)
        setLatest({ id: v.id, state: v.state })
        void message.success(t('designer.savedAsDraft'))
        void load()
      } catch (e) {
        if (e instanceof ApiError) void message.error(e.message)
      }
    })()
  }

  const doPublish = () => {
    if (!workspaceId || !latest) return
    if (latest.state === 'published') {
      void message.info(t('designer.alreadyPublished'))
      return
    }
    void (async () => {
      try {
        await publishVersion(workspaceId, ruleId, latest.id)
        void message.success(t('designer.publishedOk'))
        void load()
      } catch (e) {
        if (e instanceof ApiError) void message.error(e.message)
      }
    })()
  }

  if (!workspaceId) return null

  return (
    <div className="rule-editor">
      <Breadcrumb
        className="rule-editor__crumb"
        items={[
          { title: <Link to="/app/rules">{t('nav.rules')}</Link> },
          { title: title || '…' },
        ]}
      />
      <div className="rule-editor__title-row">
        <h2 className="rule-editor__title">{title || '—'}</h2>
      </div>
      <div className="rule-editor__toolbar">
        <div className="rule-editor__toolbar-left" />
        <div className="rule-editor__toolbar-right">
          <Select
            placeholder={t('designer.addNode')}
            options={addTypeOptions}
            onChange={(v) => v && addNode(String(v))}
            style={{ width: 160 }}
            allowClear
          />
          <Button onClick={save}>{t('designer.save')}</Button>
          <Button type="primary" onClick={doPublish}>
            {t('designer.publish')}
          </Button>
        </div>
      </div>
      <p className="rule-editor__hint">{t('designer.hint')}</p>
      <div className="rule-editor__body">
        <div className="rule-editor__main">
          <div className="rule-editor__canvas">
            <ReactFlow
              className="rule-editor__flow"
              nodeTypes={nodeTypes}
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              defaultEdgeOptions={defaultEdgeOptions}
              fitView
              proOptions={{ hideAttribution: true }}
            >
              <Background
                id="minerva-dots"
                variant={BackgroundVariant.Dots}
                gap={20}
                size={1.2}
                color="#b8c3cd"
              />
              <Controls position="bottom-left" showInteractive={false} />
              <MiniMap
                pannable
                zoomable
                nodeStrokeWidth={2}
                maskColor="rgba(241, 245, 249, 0.78)"
                style={{ background: '#ffffff' }}
                nodeColor={(n) => {
                  const t = (n.data as { nodeType?: string } | undefined)?.nodeType
                  if (t === 'start') return '#10b981'
                  if (t === 'end') return '#f87171'
                  if (t === 'branch') return '#f59e0b'
                  if (t === 'noop') return '#94a3b8'
                  return '#3b82f6'
                }}
              />
            </ReactFlow>
          </div>
        </div>
      </div>
    </div>
  )
}
