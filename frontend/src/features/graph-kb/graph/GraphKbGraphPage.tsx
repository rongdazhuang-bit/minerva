/** Graph tab: paginated entity/relation tables plus a graph-view subgraph canvas. */

import { useQuery } from '@tanstack/react-query'
import { Card, Descriptions, Empty, Form, Input, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '@/app/AuthContext'
import { useGraphKbId } from '@/features/graph-kb/shared/GraphKbContext'
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'
import {
  getGraphKbGraphView,
  listGraphKbEntities,
  listGraphKbRelations,
  type GraphKbEntityOut,
  type GraphKbRelationOut,
} from '@/features/graph-kb/api/graphKb'
import { GraphKbCanvas } from '@/features/graph-kb/graph/GraphKbCanvas'
import './GraphKbGraphPage.css'

/** Vertical space reserved below each table body for pagination. */
const TABLE_SCROLL_GUTTER_PX = 48

type EntityFilterValues = {
  name?: string
  entity_type?: string
}

type SeedView = {
  /** Projection UUID or engine entity id sent to graph-view. */
  seedEntityId: string
  hops: 1 | 2
  /** Node id highlighted on the canvas (usually engine_entity_id). */
  highlightId: string
}

/** Graph view tab at `/app/graph-kb/:graphId/graph`. */
export function GraphKbGraphPage() {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const graphId = useGraphKbId()
  const [filterForm] = Form.useForm<EntityFilterValues>()
  const [entityPage, setEntityPage] = useState(1)
  const [relationPage, setRelationPage] = useState(1)
  /** Applied entity name / type filters (not the draft form values). */
  const [filters, setFilters] = useState<EntityFilterValues>({})
  /** Current subgraph seed; canvas never loads without this. */
  const [seedView, setSeedView] = useState<SeedView | null>(null)
  const entityWrapRef = useRef<HTMLDivElement | null>(null)
  const relationWrapRef = useRef<HTMLDivElement | null>(null)
  const [entityScrollY, setEntityScrollY] = useState(180)
  const [relationScrollY, setRelationScrollY] = useState(180)

  const entityQ = useQuery({
    queryKey: ['graph-kb-entities', workspaceId, graphId, entityPage, filters],
    queryFn: () =>
      listGraphKbEntities(workspaceId!, graphId, {
        page: entityPage,
        page_size: DEFAULT_PAGE_SIZE,
        name: filters.name,
        entity_type: filters.entity_type,
      }),
    enabled: Boolean(workspaceId && graphId),
  })

  const relationQ = useQuery({
    queryKey: ['graph-kb-relations', workspaceId, graphId, relationPage],
    queryFn: () =>
      listGraphKbRelations(workspaceId!, graphId, { page: relationPage, page_size: DEFAULT_PAGE_SIZE }),
    enabled: Boolean(workspaceId && graphId),
  })

  const viewQ = useQuery({
    queryKey: ['graph-kb-graph-view', workspaceId, graphId, seedView],
    queryFn: () =>
      getGraphKbGraphView(workspaceId!, graphId, {
        seed_entity_id: seedView!.seedEntityId,
        hops: seedView!.hops,
      }),
    enabled: Boolean(workspaceId && graphId && seedView),
  })

  /** Measure table body heights so only the table body scrolls. */
  useLayoutEffect(() => {
    const entityWrap = entityWrapRef.current
    const relationWrap = relationWrapRef.current
    const measure = () => {
      if (entityWrap) {
        setEntityScrollY(Math.max(120, Math.floor(entityWrap.getBoundingClientRect().height - TABLE_SCROLL_GUTTER_PX)))
      }
      if (relationWrap) {
        setRelationScrollY(
          Math.max(120, Math.floor(relationWrap.getBoundingClientRect().height - TABLE_SCROLL_GUTTER_PX)),
        )
      }
    }
    measure()
    const ro = new ResizeObserver(measure)
    if (entityWrap) ro.observe(entityWrap)
    if (relationWrap) ro.observe(relationWrap)
    return () => ro.disconnect()
  }, [entityQ.data?.items?.length, relationQ.data?.items?.length, workspaceId])

  /** Seed the canvas from a table row (1 hop) without dumping all entities. */
  const seedFromEntity = useCallback((row: GraphKbEntityOut) => {
    setSeedView({ seedEntityId: row.id, hops: 1, highlightId: row.engine_entity_id })
  }, [])

  /** Node click: always re-request hops=2 for that seed. */
  const onCanvasNodeClick = useCallback((nodeId: string) => {
    setSeedView({ seedEntityId: nodeId, hops: 2, highlightId: nodeId })
  }, [])

  const entityColumns: ColumnsType<GraphKbEntityOut> = useMemo(
    () => [
      { title: t('graphKb.graph.column.name'), dataIndex: 'name', key: 'name', ellipsis: true },
      { title: t('graphKb.graph.column.type'), dataIndex: 'entity_type', key: 'entity_type', width: 120, ellipsis: true },
      {
        title: t('graphKb.graph.column.description'),
        dataIndex: 'description',
        key: 'description',
        ellipsis: true,
      },
    ],
    [t],
  )

  const relationColumns: ColumnsType<GraphKbRelationOut> = useMemo(
    () => [
      { title: t('graphKb.graph.column.from'), dataIndex: 'from_entity_id', key: 'from_entity_id', ellipsis: true },
      { title: t('graphKb.graph.column.to'), dataIndex: 'to_entity_id', key: 'to_entity_id', ellipsis: true },
      {
        title: t('graphKb.graph.column.relation'),
        dataIndex: 'relation_type',
        key: 'relation_type',
        width: 140,
        ellipsis: true,
      },
    ],
    [t],
  )

  const focusNode = useMemo(() => {
    const highlight = seedView?.highlightId
    if (!highlight) return null
    return (viewQ.data?.nodes ?? []).find((row) => String(row.id ?? '') === highlight) ?? null
  }, [seedView?.highlightId, viewQ.data?.nodes])

  if (!workspaceId) {
    return <Empty description={t('settings.ocrNoWorkspace')} style={{ color: 'var(--minerva-ink)' }} />
  }

  const emptyProjection = !entityQ.isLoading && (entityQ.data?.total ?? 0) === 0 && !filters.name && !filters.entity_type

  return (
    <div className="minerva-graph-kb-graph-page">
      <Card
        size="small"
        variant="borderless"
        className="minerva-graph-kb-graph-page__card minerva-page-shell-card"
      >
        {emptyProjection ? (
          <div className="minerva-graph-kb-graph-page__empty">
            <Empty description={t('graphKb.emptyNeedIndex')} />
          </div>
        ) : (
          <div className="minerva-graph-kb-graph-page__split">
            <div className="minerva-graph-kb-graph-page__tables">
              <Form
                form={filterForm}
                layout="inline"
                className="minerva-graph-kb-graph-page__filter"
                onValuesChange={(_, values) => {
                  setEntityPage(1)
                  setFilters({
                    name: values.name?.trim() || undefined,
                    entity_type: values.entity_type?.trim() || undefined,
                  })
                }}
              >
                <Form.Item name="name" label={t('graphKb.graph.filter.name')}>
                  <Input allowClear placeholder={t('graphKb.graph.filter.namePh')} />
                </Form.Item>
                <Form.Item name="entity_type" label={t('graphKb.graph.filter.type')}>
                  <Input allowClear placeholder={t('graphKb.graph.filter.typePh')} />
                </Form.Item>
              </Form>

              <Typography.Text className="minerva-graph-kb-graph-page__section">
                {t('graphKb.graph.entities')}
              </Typography.Text>
              <div ref={entityWrapRef} className="minerva-graph-kb-graph-page__table-wrap">
                <Table<GraphKbEntityOut>
                  className="minerva-graph-kb-graph-page__table minerva-card-table-scroll-ocr"
                  rowKey="id"
                  size="small"
                  loading={entityQ.isLoading}
                  columns={entityColumns}
                  dataSource={entityQ.data?.items ?? []}
                  locale={{ emptyText: t('graphKb.emptyNeedIndex') }}
                  rowClassName={(row) =>
                    seedView?.seedEntityId === row.id || seedView?.highlightId === row.engine_entity_id
                      ? 'minerva-graph-kb-graph-page__row--active'
                      : ''
                  }
                  onRow={(row) => ({ onClick: () => seedFromEntity(row) })}
                  scroll={{ y: entityScrollY }}
                  sticky
                  pagination={{
                    current: entityPage,
                    pageSize: DEFAULT_PAGE_SIZE,
                    total: entityQ.data?.total ?? 0,
                    showSizeChanger: false,
                    size: 'small',
                    onChange: (next) => setEntityPage(next),
                  }}
                />
              </div>

              <Typography.Text className="minerva-graph-kb-graph-page__section">
                {t('graphKb.graph.relations')}
              </Typography.Text>
              <div ref={relationWrapRef} className="minerva-graph-kb-graph-page__table-wrap">
                <Table<GraphKbRelationOut>
                  className="minerva-graph-kb-graph-page__table minerva-card-table-scroll-ocr"
                  rowKey="id"
                  size="small"
                  loading={relationQ.isLoading}
                  columns={relationColumns}
                  dataSource={relationQ.data?.items ?? []}
                  locale={{ emptyText: t('graphKb.emptyNeedIndex') }}
                  onRow={(row) => ({
                    onClick: () =>
                      setSeedView({
                        seedEntityId: row.from_entity_id,
                        hops: 1,
                        highlightId: row.from_entity_id,
                      }),
                  })}
                  scroll={{ y: relationScrollY }}
                  sticky
                  pagination={{
                    current: relationPage,
                    pageSize: DEFAULT_PAGE_SIZE,
                    total: relationQ.data?.total ?? 0,
                    showSizeChanger: false,
                    size: 'small',
                    onChange: (next) => setRelationPage(next),
                  }}
                />
              </div>
            </div>

            <div className="minerva-graph-kb-graph-page__canvas-col">
              <GraphKbCanvas
                nodes={viewQ.data?.nodes ?? []}
                edges={viewQ.data?.edges ?? []}
                seedId={seedView?.highlightId}
                loading={viewQ.isFetching}
                emptyHint={t('graphKb.graph.canvasHint')}
                onNodeClick={onCanvasNodeClick}
              />
              {focusNode ? (
                <Descriptions
                  size="small"
                  column={1}
                  className="minerva-graph-kb-graph-page__detail"
                  title={t('graphKb.graph.selectedNode')}
                >
                  <Descriptions.Item label={t('graphKb.graph.column.name')}>
                    {String(focusNode.name ?? focusNode.id ?? '—')}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('graphKb.graph.column.type')}>
                    {String(focusNode.entity_type ?? '—')}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('graphKb.graph.column.description')}>
                    {String(focusNode.description ?? '—')}
                  </Descriptions.Item>
                </Descriptions>
              ) : null}
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}
