/** Summaries tab: community/topic tree; click loads a community subgraph. */

import { useQuery } from '@tanstack/react-query'
import { Card, Empty, Spin, Tree, Typography } from 'antd'
import type { DataNode } from 'antd/es/tree'
import { useCallback, useMemo, useState, type Key } from 'react'
import { useTranslation } from 'react-i18next'
import { useGraphKbId } from '@/features/graph-kb/shared/GraphKbContext'
import { useAuth } from '@/app/AuthContext'
import {
  getGraphKbGraphView,
  listGraphKbSummaries,
  type GraphKbSummaryOut,
} from '@/features/graph-kb/api/graphKb'
import { GraphKbCanvas } from '@/features/graph-kb/graph/GraphKbCanvas'
import './GraphKbSummariesPage.css'

/** Page size used only to collapse summary pages into one tree. */
const SUMMARY_FETCH_PAGE_SIZE = 100

type CanvasQuery =
  | { kind: 'community'; communityId: string }
  | { kind: 'seed'; seedEntityId: string; hops: 2 }

/** Fetch every summary page so the community tree is complete. */
async function listAllGraphKbSummaries(workspaceId: string, graphId: string) {
  const first = await listGraphKbSummaries(workspaceId, graphId, {
    page: 1,
    page_size: SUMMARY_FETCH_PAGE_SIZE,
  })
  const items = [...first.items]
  const pages = Math.max(1, Math.ceil(first.total / SUMMARY_FETCH_PAGE_SIZE))
  for (let page = 2; page <= pages; page += 1) {
    const next = await listGraphKbSummaries(workspaceId, graphId, {
      page,
      page_size: SUMMARY_FETCH_PAGE_SIZE,
    })
    items.push(...next.items)
  }
  return { items, total: first.total }
}

/** Build an Ant Tree from flat summaries linked by parent_id. */
export function buildSummaryTree(
  items: GraphKbSummaryOut[],
  untitled: string,
): { tree: DataNode[]; byId: Map<string, GraphKbSummaryOut> } {
  const byId = new Map(items.map((row) => [row.id, row]))
  const children = new Map<string, GraphKbSummaryOut[]>()
  const roots: GraphKbSummaryOut[] = []
  for (const row of items) {
    const parentId = row.parent_id
    if (parentId && byId.has(parentId)) {
      const list = children.get(parentId) ?? []
      list.push(row)
      children.set(parentId, list)
    } else {
      roots.push(row)
    }
  }

  /** Recursively map a summary row to a Tree node. */
  const toNode = (row: GraphKbSummaryOut): DataNode => ({
    key: row.id,
    title: row.title?.trim() || untitled,
    children: (children.get(row.id) ?? []).map(toNode),
  })

  return { tree: roots.map(toNode), byId }
}

/** Summaries tab at `/app/graph-kb/:graphId/summaries`. */
export function GraphKbSummariesPage() {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const graphId = useGraphKbId()
  /** Selected community projection id (graph-view community_id). */
  const [selectedId, setSelectedId] = useState<string | null>(null)
  /** Canvas query: community click, or hops=2 after a node click. */
  const [canvasQuery, setCanvasQuery] = useState<CanvasQuery | null>(null)

  const listQ = useQuery({
    queryKey: ['graph-kb-summaries-all', workspaceId, graphId],
    queryFn: () => listAllGraphKbSummaries(workspaceId!, graphId),
    enabled: Boolean(workspaceId && graphId),
  })

  const viewQ = useQuery({
    queryKey: ['graph-kb-graph-view', workspaceId, graphId, canvasQuery],
    queryFn: () => {
      if (!canvasQuery) throw new Error('missing canvas query')
      if (canvasQuery.kind === 'community') {
        return getGraphKbGraphView(workspaceId!, graphId, { community_id: canvasQuery.communityId, hops: 1 })
      }
      return getGraphKbGraphView(workspaceId!, graphId, {
        seed_entity_id: canvasQuery.seedEntityId,
        hops: canvasQuery.hops,
      })
    },
    enabled: Boolean(workspaceId && graphId && canvasQuery),
  })

  const { tree, byId } = useMemo(
    () => buildSummaryTree(listQ.data?.items ?? [], t('graphKb.summaries.untitled')),
    [listQ.data?.items, t],
  )

  const selected = selectedId ? byId.get(selectedId) : undefined

  /** Tree click loads the community subgraph (not a full entity dump). */
  const onSelect = useCallback((keys: Key[]) => {
    const id = keys[0] != null ? String(keys[0]) : null
    setSelectedId(id)
    setCanvasQuery(id ? { kind: 'community', communityId: id } : null)
  }, [])

  /** Node click: request hops=2 for that seed. */
  const onCanvasNodeClick = useCallback((nodeId: string) => {
    setCanvasQuery({ kind: 'seed', seedEntityId: nodeId, hops: 2 })
  }, [])

  if (!workspaceId) {
    return <Empty description={t('settings.ocrNoWorkspace')} style={{ color: 'var(--minerva-ink)' }} />
  }

  const emptyProjection = !listQ.isLoading && (listQ.data?.total ?? 0) === 0

  return (
    <div className="minerva-graph-kb-summaries-page">
      <Card
        size="small"
        variant="borderless"
        className="minerva-graph-kb-summaries-page__card minerva-page-shell-card"
      >
        {emptyProjection ? (
          <div className="minerva-graph-kb-summaries-page__empty">
            <Empty description={t('graphKb.emptyNeedIndex')} />
          </div>
        ) : (
          <div className="minerva-graph-kb-summaries-page__split">
            <div className="minerva-graph-kb-summaries-page__tree-col">
              <Typography.Text className="minerva-graph-kb-summaries-page__section">
                {t('graphKb.summaries.tree')}
              </Typography.Text>
              <Spin spinning={listQ.isLoading}>
                <div className="minerva-graph-kb-summaries-page__tree minerva-scrollbar-styled">
                  <Tree
                    blockNode
                    treeData={tree}
                    selectedKeys={selectedId ? [selectedId] : []}
                    onSelect={onSelect}
                  />
                </div>
              </Spin>
              <Typography.Text className="minerva-graph-kb-summaries-page__section">
                {t('graphKb.summaries.detail')}
              </Typography.Text>
              <div className="minerva-graph-kb-summaries-page__detail minerva-scrollbar-thin">
                {selected?.summary ? (
                  <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
                    {selected.summary}
                  </Typography.Paragraph>
                ) : (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={t('graphKb.summaries.pick')}
                  />
                )}
              </div>
            </div>
            <div className="minerva-graph-kb-summaries-page__canvas-col">
              <GraphKbCanvas
                nodes={viewQ.data?.nodes ?? []}
                edges={viewQ.data?.edges ?? []}
                seedId={canvasQuery?.kind === 'seed' ? canvasQuery.seedEntityId : undefined}
                loading={viewQ.isFetching}
                emptyHint={t('graphKb.summaries.canvasHint')}
                onNodeClick={onCanvasNodeClick}
              />
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}
