import { addRuleVersion, getRule, publishVersion } from '@/api/rules'
import { ApiError } from '@/api/client'
import { useAuth } from '@/app/AuthContext'
import {
  addEdge,
  Background,
  Controls,
  type Connection,
  type Edge,
  type Node,
  type NodeTypes,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Breadcrumb, Button, Select, Space, message } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'

function MinervaNode(p: { data: { nodeType: string; label: string } }) {
  return (
    <div
      style={{
        minWidth: 100,
        padding: '8px 12px',
        borderRadius: 6,
        background: 'linear-gradient(180deg, #1e2630, #12161c)',
        border: '1px solid #c9a227',
        color: '#e8e4dc',
        fontSize: 13,
      }}
    >
      <Handle
        type="target"
        position={Position.Top}
        style={{ background: '#c9a227' }}
      />
      <div style={{ textAlign: 'center' }}>{p.data.label || p.data.nodeType}</div>
      <Handle
        type="source"
        position={Position.Bottom}
        style={{ background: '#c9a227' }}
      />
    </div>
  )
}

const MINERVA: NodeTypes = { minerva: MinervaNode }

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
      edges: [{ id: 'e1', source: 'a', target: 'b' }],
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

const ADD_TYPES = [
  { value: 'start', label: 'start' },
  { value: 'end', label: 'end' },
  { value: 'branch', label: 'branch' },
  { value: 'noop', label: 'noop' },
]

export function RuleEditorPage() {
  const { ruleId = '' } = useParams()
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const [title, setTitle] = useState('')
  const [latest, setLatest] = useState<{ id: string; state: string } | null>(null)
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])

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
    (c: Connection) => setEdges((e) => addEdge({ id: `e-${crypto.randomUUID()}`, ...c }, e)),
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
        void message.success('已保存为新版本')
        void load()
      } catch (e) {
        if (e instanceof ApiError) void message.error(e.message)
      }
    })()
  }

  const doPublish = () => {
    if (!workspaceId || !latest) return
    if (latest.state === 'published') {
      void message.info('当前版本已发布')
      return
    }
    void (async () => {
      try {
        await publishVersion(workspaceId, ruleId, latest.id)
        void message.success('已发布')
        void load()
      } catch (e) {
        if (e instanceof ApiError) void message.error(e.message)
      }
    })()
  }

  if (!workspaceId) return null

  return (
    <div>
      <Breadcrumb
        style={{ marginBottom: 12 }}
        items={[
          { title: <Link to="/app/rules">{t('nav.rules')}</Link> },
          { title: title || '…' },
        ]}
      />
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <h2 style={{ margin: 0, fontFamily: "'Fraunces', Georgia, serif" }}>{title || '—'}</h2>
        <Space>
          <Select
            placeholder="添加节点"
            options={ADD_TYPES}
            onChange={addNode}
            style={{ width: 120 }}
            allowClear
          />
          <Button onClick={save}>{t('designer.save')}</Button>
          <Button type="primary" onClick={doPublish}>
            {t('designer.publish')}
          </Button>
        </Space>
      </div>
      <p style={{ color: '#8a919b', fontSize: 12, margin: '0 0 8px' }}>{t('designer.hint')}</p>
      <div style={{ width: '100%', height: 520, border: '1px solid #1e2630', borderRadius: 8, overflow: 'hidden' }}>
        <ReactFlow
          nodeTypes={MINERVA}
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          fitView
        >
          <Background color="#1e2630" />
          <Controls />
          <MiniMap />
        </ReactFlow>
      </div>
    </div>
  )
}
