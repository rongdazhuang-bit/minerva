import { CopyOutlined, ReadOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { Alert, Button, Descriptions, Empty, Input, Space, Spin, Typography } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  listMcpClientResources,
  readMcpClientResource,
  type McpClientListItem,
  type McpReadResourceResult,
  type McpResource,
  type McpResourceContent,
} from '@/api/mcp'
import { useAppMessage } from '@/app/useAppMessage'
import {
  filterMcpResources,
  resourceDisplayName,
  splitTextHighlight,
} from './mcpResourceListUtils'
import './McpToolExplorerModal.css'

const { Text } = Typography

const EMPTY_FIELD = '—'

export type McpResourcesExplorerPanelProps = {
  client: McpClientListItem
  workspaceId: string
  active: boolean
}

/** Format read_resource content blocks for display in the result area. */
function formatResourceContents(contents: McpResourceContent[] | undefined): string {
  if (!contents?.length) return ''
  const blocks = contents.map((block) => {
    if (block.text != null) {
      try {
        return JSON.stringify(JSON.parse(block.text), null, 2)
      } catch {
        return block.text
      }
    }
    if (block.blob != null) {
      return JSON.stringify({ mimeType: block.mimeType, blob: block.blob }, null, 2)
    }
    return JSON.stringify(block, null, 2)
  })
  return blocks.length === 1 ? blocks[0] : JSON.stringify(contents, null, 2)
}

/** Resources list / read debugger panel for one saved MCP client. */
export function McpResourcesExplorerPanel({
  client,
  workspaceId,
  active,
}: McpResourcesExplorerPanelProps) {
  const { t } = useTranslation()
  const messageApi = useAppMessage()
  const [resources, setResources] = useState<McpResource[]>([])
  const [selectedResource, setSelectedResource] = useState<McpResource | null>(null)
  const [search, setSearch] = useState('')
  const [readResult, setReadResult] = useState<McpReadResourceResult | null>(null)
  const [loadingList, setLoadingList] = useState(false)
  const [loadingRead, setLoadingRead] = useState(false)
  const [listError, setListError] = useState<string | null>(null)
  const [loadedOnce, setLoadedOnce] = useState(false)

  const fetchResources = useCallback(async () => {
    setLoadingList(true)
    setListError(null)
    try {
      const res = await listMcpClientResources(workspaceId, client.id)
      setLoadedOnce(true)
      if (!res.ok) {
        setResources([])
        setListError(
          res.error_message || t('mcp.toolExplorer.listResourcesFailed', { defaultValue: '获取资源列表失败' }),
        )
        return
      }
      setResources(res.resources)
      setSelectedResource((prev) => prev ?? res.resources[0] ?? null)
    } catch (err) {
      setLoadedOnce(true)
      setResources([])
      setListError(
        err instanceof Error
          ? err.message
          : t('mcp.toolExplorer.listResourcesFailed', { defaultValue: '获取资源列表失败' }),
      )
    } finally {
      setLoadingList(false)
    }
  }, [client.id, t, workspaceId])

  useEffect(() => {
    setLoadedOnce(false)
    setResources([])
    setSelectedResource(null)
    setReadResult(null)
    setSearch('')
    setListError(null)
  }, [client.id])

  useEffect(() => {
    if (active && !loadedOnce) {
      void fetchResources()
    }
  }, [active, loadedOnce, fetchResources])

  const filteredResources = useMemo(() => filterMcpResources(resources, search), [resources, search])

  useEffect(() => {
    if (filteredResources.length === 0) {
      setSelectedResource(null)
      return
    }
    setSelectedResource((prev) => {
      if (prev && filteredResources.some((resource) => resource.uri === prev.uri)) return prev
      return filteredResources[0]
    })
  }, [filteredResources])

  const handleClear = () => {
    setSelectedResource(null)
    setReadResult(null)
  }

  const readResource = async () => {
    if (!selectedResource) return
    setLoadingRead(true)
    setReadResult(null)
    try {
      const res = await readMcpClientResource(workspaceId, client.id, selectedResource.uri)
      setReadResult(res)
      if (!res.ok) {
        messageApi.error(
          res.error_message || t('mcp.toolExplorer.readResourceFailed', { defaultValue: '读取资源失败' }),
        )
      }
    } catch (err) {
      messageApi.error(
        err instanceof Error
          ? err.message
          : t('mcp.toolExplorer.readResourceFailed', { defaultValue: '读取资源失败' }),
      )
    } finally {
      setLoadingRead(false)
    }
  }

  const copyResult = async () => {
    if (!readResult) return
    try {
      await navigator.clipboard.writeText(formatResourceContents(readResult.contents))
      messageApi.success(t('common.copied', { defaultValue: '已复制' }))
    } catch {
      messageApi.error(t('common.copyFailed', { defaultValue: '复制失败' }))
    }
  }

  const renderHighlightedText = (text: string) =>
    splitTextHighlight(text, search).map((part, index) =>
      part.match ? (
        <mark key={index} className="minerva-mcp-tool-explorer__highlight">
          {part.text}
        </mark>
      ) : (
        <span key={index}>{part.text}</span>
      ),
    )

  const resultPayload = useMemo(() => formatResourceContents(readResult?.contents), [readResult])

  return (
    <div className="minerva-mcp-tool-explorer__layout">
      <aside className="minerva-mcp-tool-explorer__sidebar">
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder={t('mcp.toolExplorer.searchResourcesPlaceholder', { defaultValue: '搜索资源' })}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label={t('mcp.toolExplorer.searchResourcesPlaceholder', { defaultValue: '搜索资源' })}
        />
        {resources.length > 0 ? (
          <Text type="secondary" className="minerva-mcp-tool-explorer__search-meta">
            {search.trim()
              ? t('mcp.toolExplorer.searchResourceCount', {
                  defaultValue: '{{matched}} / {{total}} 个资源',
                  matched: filteredResources.length,
                  total: resources.length,
                })
              : t('mcp.toolExplorer.resourceCount', {
                  defaultValue: '共 {{total}} 个资源',
                  total: resources.length,
                })}
          </Text>
        ) : null}
        <div className="minerva-mcp-tool-explorer__sidebar-actions">
          <Button icon={<ReloadOutlined />} loading={loadingList} onClick={() => void fetchResources()}>
            {t('mcp.toolExplorer.listResources', { defaultValue: 'List Resources' })}
          </Button>
          <Button onClick={handleClear}>{t('mcp.toolExplorer.clear', { defaultValue: 'Clear' })}</Button>
        </div>
        {listError ? <Alert type="error" showIcon message={listError} /> : null}
        <div className="minerva-mcp-tool-explorer__tool-list-panel minerva-scrollbar-thin">
          <Spin spinning={loadingList}>
            <div className="minerva-mcp-tool-explorer__tool-list">
              {resources.length === 0 && !loadingList ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t('common.noData', { defaultValue: '暂无数据' })}
                />
              ) : filteredResources.length === 0 ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t('mcp.toolExplorer.noResourceSearchMatch', {
                    defaultValue: '没有匹配的资源',
                  })}
                />
              ) : (
                filteredResources.map((resource, index) => (
                  <div
                    key={`${resource.uri}-${index}`}
                    className={`minerva-mcp-tool-explorer__tool-item${
                      selectedResource?.uri === resource.uri
                        ? ' minerva-mcp-tool-explorer__tool-item--active'
                        : ''
                    }`}
                    onClick={() => {
                      setSelectedResource(resource)
                      setReadResult(null)
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        setSelectedResource(resource)
                        setReadResult(null)
                      }
                    }}
                    role="button"
                    tabIndex={0}
                  >
                    <div className="minerva-mcp-tool-explorer__tool-name">
                      {renderHighlightedText(resourceDisplayName(resource))}
                    </div>
                    {resource.description ? (
                      <div className="minerva-mcp-tool-explorer__tool-desc">
                        {renderHighlightedText(resource.description)}
                      </div>
                    ) : null}
                  </div>
                ))
              )}
            </div>
          </Spin>
        </div>
      </aside>

      <main className="minerva-mcp-tool-explorer__main minerva-scrollbar-styled">
        {!selectedResource ? (
          <div className="minerva-mcp-tool-explorer__empty">
            {t('mcp.toolExplorer.selectResource', { defaultValue: '请从左侧选择一个资源' })}
          </div>
        ) : (
          <>
            <h2 className="minerva-mcp-tool-explorer__title">{resourceDisplayName(selectedResource)}</h2>
            <Descriptions column={1} bordered size="small" className="minerva-mcp-tool-explorer__section">
              <Descriptions.Item label={t('mcp.toolExplorer.resourceUri', { defaultValue: 'URI' })}>
                {selectedResource.uri || EMPTY_FIELD}
              </Descriptions.Item>
              <Descriptions.Item label={t('mcp.toolExplorer.resourceName', { defaultValue: 'Name' })}>
                {selectedResource.name?.trim() || EMPTY_FIELD}
              </Descriptions.Item>
              <Descriptions.Item
                label={t('mcp.toolExplorer.resourceDescription', { defaultValue: 'Description' })}
              >
                {selectedResource.description?.trim() || EMPTY_FIELD}
              </Descriptions.Item>
              <Descriptions.Item label={t('mcp.toolExplorer.resourceMimeType', { defaultValue: 'MIME Type' })}>
                {selectedResource.mimeType?.trim() || EMPTY_FIELD}
              </Descriptions.Item>
            </Descriptions>

            <Space style={{ marginTop: 8 }}>
              <Button
                type="primary"
                icon={<ReadOutlined />}
                loading={loadingRead}
                onClick={() => void readResource()}
              >
                {t('mcp.toolExplorer.readResource', { defaultValue: 'Read Resource' })}
              </Button>
            </Space>

            {readResult ? (
              <div
                className={`minerva-mcp-tool-explorer__result${
                  readResult.ok
                    ? ' minerva-mcp-tool-explorer__result--success'
                    : ' minerva-mcp-tool-explorer__result--error'
                }`}
              >
                <Space>
                  <Text strong>
                    {readResult.ok
                      ? t('mcp.toolExplorer.resourceResultSuccess', {
                          defaultValue: 'Resource Result: Success',
                        })
                      : t('mcp.toolExplorer.resourceResultError', {
                          defaultValue: 'Resource Result: Error',
                        })}
                  </Text>
                  {readResult.ok && resultPayload ? (
                    <Button size="small" icon={<CopyOutlined />} onClick={() => void copyResult()}>
                      {t('mcp.toolExplorer.copyResult', { defaultValue: '复制结果' })}
                    </Button>
                  ) : null}
                </Space>
                {resultPayload ? <pre>{resultPayload}</pre> : null}
                {!readResult.ok && readResult.error_message ? (
                  <Text type="danger">{readResult.error_message}</Text>
                ) : null}
              </div>
            ) : null}
          </>
        )}
      </main>
    </div>
  )
}
