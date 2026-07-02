import {
  CheckOutlined,
  CloseOutlined,
  CopyOutlined,
  ReloadOutlined,
  SearchOutlined,
  SendOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Empty,
  Input,
  InputNumber,
  Popconfirm,
  Radio,
  Space,
  Spin,
  Switch,
  Tag,
  Typography,
} from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  callMcpClientTool,
  listMcpClientTools,
  type McpCallToolResult,
  type McpClientListItem,
  type McpTool,
} from '@/api/mcp'
import { useAppMessage } from '@/app/useAppMessage'
import { filterMcpTools, splitTextHighlight } from './mcpToolListUtils'
import {
  argumentsToJsonText,
  defaultArgumentsFromFields,
  listSchemaFields,
  parseArgumentsJson,
} from './schemaFormUtils'
import './McpToolExplorerModal.css'

const { Text, Paragraph } = Typography

export type McpToolsExplorerPanelProps = {
  client: McpClientListItem
  workspaceId: string
}

type InputMode = 'form' | 'json'

/** Tools list / call debugger panel for one saved MCP client. */
export function McpToolsExplorerPanel({ client, workspaceId }: McpToolsExplorerPanelProps) {
  const { t } = useTranslation()
  const messageApi = useAppMessage()
  const [tools, setTools] = useState<McpTool[]>([])
  const [selectedTool, setSelectedTool] = useState<McpTool | null>(null)
  const [search, setSearch] = useState('')
  const [arguments_, setArguments] = useState<Record<string, unknown>>({})
  const [jsonText, setJsonText] = useState('{}')
  const [inputMode, setInputMode] = useState<InputMode>('form')
  const [result, setResult] = useState<McpCallToolResult | null>(null)
  const [loadingList, setLoadingList] = useState(false)
  const [loadingCall, setLoadingCall] = useState(false)
  const [listError, setListError] = useState<string | null>(null)

  const resetPanelState = useCallback(() => {
    setSelectedTool(null)
    setArguments({})
    setJsonText('{}')
    setResult(null)
    setInputMode('form')
  }, [])

  const fetchTools = useCallback(async () => {
    setLoadingList(true)
    setListError(null)
    try {
      const res = await listMcpClientTools(workspaceId, client.id)
      if (!res.ok) {
        setTools([])
        setListError(res.error_message || t('mcp.toolExplorer.listFailed', { defaultValue: '获取工具列表失败' }))
        return
      }
      setTools(res.tools)
      setSelectedTool((prev) => prev ?? res.tools[0] ?? null)
    } catch (err) {
      setTools([])
      setListError(err instanceof Error ? err.message : t('mcp.toolExplorer.listFailed', { defaultValue: '获取工具列表失败' }))
    } finally {
      setLoadingList(false)
    }
  }, [client.id, t, workspaceId])

  useEffect(() => {
    setSearch('')
    resetPanelState()
    void fetchTools()
  }, [client.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const filteredTools = useMemo(() => filterMcpTools(tools, search), [search, tools])

  useEffect(() => {
    if (filteredTools.length === 0) {
      setSelectedTool(null)
      return
    }
    setSelectedTool((prev) => {
      if (prev && filteredTools.some((tool) => tool.name === prev.name)) return prev
      return filteredTools[0]
    })
  }, [filteredTools])

  const schemaFields = useMemo(
    () => listSchemaFields(selectedTool?.inputSchema),
    [selectedTool],
  )

  useEffect(() => {
    if (!selectedTool) return
    const defaults = defaultArgumentsFromFields(schemaFields)
    setArguments(defaults)
    setJsonText(argumentsToJsonText(defaults))
    setResult(null)
    setInputMode(schemaFields.length > 0 ? 'form' : 'json')
  }, [selectedTool, schemaFields])

  const selectTool = (tool: McpTool) => {
    setSelectedTool(tool)
  }

  const handleClear = () => {
    resetPanelState()
  }

  const resolveArguments = (): Record<string, unknown> | null => {
    if (inputMode === 'json') {
      try {
        return parseArgumentsJson(jsonText)
      } catch {
        messageApi.error(t('mcp.toolExplorer.invalidJson', { defaultValue: 'JSON 格式无效' }))
        return null
      }
    }
    for (const field of schemaFields) {
      if (field.required) {
        const value = arguments_[field.key]
        if (value === undefined || value === null || value === '') {
          messageApi.error(
            t('mcp.toolExplorer.requiredField', {
              defaultValue: '请填写必填项：{{field}}',
              field: field.key,
            }),
          )
          return null
        }
      }
    }
    return arguments_
  }

  const runTool = async () => {
    if (!selectedTool) return
    const args = resolveArguments()
    if (args == null) return
    setLoadingCall(true)
    setResult(null)
    try {
      const res = await callMcpClientTool(workspaceId, client.id, selectedTool.name, args)
      setResult(res)
      if (!res.ok) {
        messageApi.error(res.error_message || t('mcp.toolExplorer.callFailed', { defaultValue: '工具调用失败' }))
      }
    } catch (err) {
      messageApi.error(err instanceof Error ? err.message : t('mcp.toolExplorer.callFailed', { defaultValue: '工具调用失败' }))
    } finally {
      setLoadingCall(false)
    }
  }

  const copyInput = async () => {
    const args = inputMode === 'json' ? jsonText : argumentsToJsonText(arguments_)
    try {
      await navigator.clipboard.writeText(args)
      messageApi.success(t('common.copied', { defaultValue: '已复制' }))
    } catch {
      messageApi.error(t('common.copyFailed', { defaultValue: '复制失败' }))
    }
  }

  const copyResult = async () => {
    if (!result) return
    try {
      await navigator.clipboard.writeText(JSON.stringify(result, null, 2))
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

  const renderAnnotationTag = (label: string, active: boolean) => (
    <Tag color={active ? 'green' : 'default'}>
      {active ? <CheckOutlined /> : <CloseOutlined />} {label}
    </Tag>
  )

  const renderFormField = (field: (typeof schemaFields)[number]) => {
    const label = (
      <span>
        {field.key}
        {field.required ? <Text type="danger"> *</Text> : null}
      </span>
    )
    const value = arguments_[field.key]
    const onChange = (next: unknown) => {
      setArguments((prev) => {
        const updated = { ...prev, [field.key]: next }
        setJsonText(argumentsToJsonText(updated))
        return updated
      })
    }

    if (field.kind === 'boolean') {
      return (
        <div key={field.key} className="minerva-mcp-tool-explorer__section">
          <Space>
            {label}
            <Switch checked={Boolean(value)} onChange={(checked) => onChange(checked)} />
          </Space>
        </div>
      )
    }
    if (field.kind === 'number' || field.kind === 'integer') {
      return (
        <div key={field.key} className="minerva-mcp-tool-explorer__section">
          <Text>{label}</Text>
          <InputNumber
            style={{ width: '100%', marginTop: 4 }}
            value={typeof value === 'number' ? value : undefined}
            onChange={(num) => onChange(num ?? undefined)}
          />
        </div>
      )
    }
    if (field.kind === 'array' || field.kind === 'object' || field.kind === 'unknown') {
      return (
        <div key={field.key} className="minerva-mcp-tool-explorer__section">
          <Text>{label}</Text>
          <Input.TextArea
            rows={3}
            style={{ marginTop: 4 }}
            value={
              typeof value === 'string'
                ? value
                : JSON.stringify(value ?? (field.kind === 'array' ? [] : {}))
            }
            onChange={(e) => {
              try {
                onChange(JSON.parse(e.target.value))
              } catch {
                onChange(e.target.value)
              }
            }}
          />
        </div>
      )
    }
    return (
      <div key={field.key} className="minerva-mcp-tool-explorer__section">
        <Text>{label}</Text>
        <Input.TextArea
          rows={2}
          allowClear
          style={{ marginTop: 4 }}
          value={typeof value === 'string' ? value : String(value ?? '')}
          onChange={(e) => onChange(e.target.value)}
        />
        {field.description ? (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {field.description}
          </Text>
        ) : null}
      </div>
    )
  }

  const resultPayload = useMemo(() => {
    if (!result) return ''
    if (result.structuredContent) {
      return JSON.stringify(result.structuredContent, null, 2)
    }
    if (result.content?.length) {
      return JSON.stringify(result.content, null, 2)
    }
    return JSON.stringify(result, null, 2)
  }, [result])

  const runButton = (
    <Button type="primary" icon={<SendOutlined />} loading={loadingCall} onClick={() => void runTool()}>
      {t('mcp.toolExplorer.runTool', { defaultValue: 'Run Tool' })}
    </Button>
  )

  return (
    <div className="minerva-mcp-tool-explorer__layout">
      <aside className="minerva-mcp-tool-explorer__sidebar minerva-scrollbar-styled">
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder={t('mcp.toolExplorer.searchPlaceholder', { defaultValue: '搜索工具' })}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label={t('mcp.toolExplorer.searchPlaceholder', { defaultValue: '搜索工具' })}
        />
        {tools.length > 0 ? (
          <Text type="secondary" className="minerva-mcp-tool-explorer__search-meta">
            {search.trim()
              ? t('mcp.toolExplorer.searchCount', {
                  defaultValue: '{{matched}} / {{total}} 个工具',
                  matched: filteredTools.length,
                  total: tools.length,
                })
              : t('mcp.toolExplorer.toolCount', {
                  defaultValue: '共 {{total}} 个工具',
                  total: tools.length,
                })}
          </Text>
        ) : null}
        <div className="minerva-mcp-tool-explorer__sidebar-actions">
          <Button icon={<ReloadOutlined />} loading={loadingList} onClick={() => void fetchTools()}>
            {t('mcp.toolExplorer.listTools', { defaultValue: 'List Tools' })}
          </Button>
          <Button onClick={handleClear}>{t('mcp.toolExplorer.clear', { defaultValue: 'Clear' })}</Button>
        </div>
        {listError ? <Alert type="error" showIcon message={listError} /> : null}
        <div className="minerva-mcp-tool-explorer__tool-list-panel">
          <Spin spinning={loadingList}>
            <div className="minerva-mcp-tool-explorer__tool-list minerva-scrollbar-styled">
              {tools.length === 0 && !loadingList ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t('common.noData', { defaultValue: '暂无数据' })}
                />
              ) : filteredTools.length === 0 ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t('mcp.toolExplorer.noSearchMatch', {
                    defaultValue: '没有匹配的工具',
                  })}
                />
              ) : (
                filteredTools.map((tool) => (
                  <div
                    key={tool.name}
                    className={`minerva-mcp-tool-explorer__tool-item${
                      selectedTool?.name === tool.name ? ' minerva-mcp-tool-explorer__tool-item--active' : ''
                    }`}
                    onClick={() => selectTool(tool)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') selectTool(tool)
                    }}
                    role="button"
                    tabIndex={0}
                  >
                    <div className="minerva-mcp-tool-explorer__tool-name">
                      {renderHighlightedText(tool.name)}
                    </div>
                    {tool.description ? (
                      <div className="minerva-mcp-tool-explorer__tool-desc">
                        {renderHighlightedText(tool.description)}
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
        {!selectedTool ? (
          <div className="minerva-mcp-tool-explorer__empty">
            {t('mcp.toolExplorer.selectTool', { defaultValue: '请从左侧选择一个工具' })}
          </div>
        ) : (
          <>
            <h2 className="minerva-mcp-tool-explorer__title">{selectedTool.name}</h2>
            {selectedTool.description ? <Paragraph type="secondary">{selectedTool.description}</Paragraph> : null}
            <div className="minerva-mcp-tool-explorer__tags">
              {renderAnnotationTag(
                t('mcp.toolExplorer.readOnly', { defaultValue: 'Read-only' }),
                selectedTool.annotations.readOnlyHint,
              )}
              {renderAnnotationTag(
                t('mcp.toolExplorer.destructive', { defaultValue: 'Destructive' }),
                selectedTool.annotations.destructiveHint,
              )}
              {renderAnnotationTag(
                t('mcp.toolExplorer.idempotent', { defaultValue: 'Idempotent' }),
                selectedTool.annotations.idempotentHint,
              )}
              {renderAnnotationTag(
                t('mcp.toolExplorer.openWorld', { defaultValue: 'Open-world' }),
                selectedTool.annotations.openWorldHint,
              )}
            </div>

            <div className="minerva-mcp-tool-explorer__section">
              <Radio.Group
                value={inputMode}
                onChange={(e) => {
                  const mode = e.target.value as InputMode
                  setInputMode(mode)
                  if (mode === 'json') {
                    setJsonText(argumentsToJsonText(arguments_))
                  }
                }}
                optionType="button"
                buttonStyle="solid"
                options={[
                  { label: t('mcp.toolExplorer.formMode', { defaultValue: '表单' }), value: 'form' },
                  { label: t('mcp.toolExplorer.jsonMode', { defaultValue: 'JSON' }), value: 'json' },
                ]}
              />
            </div>

            {inputMode === 'form' ? (
              schemaFields.length > 0 ? (
                schemaFields.map(renderFormField)
              ) : (
                <Alert
                  type="info"
                  showIcon
                  message={t('mcp.toolExplorer.noSchema', { defaultValue: '无 inputSchema，请使用 JSON 模式' })}
                />
              )
            ) : (
              <Input.TextArea rows={8} value={jsonText} onChange={(e) => setJsonText(e.target.value)} />
            )}

            <Space style={{ marginTop: 8 }}>
              {selectedTool.annotations.destructiveHint ? (
                <Popconfirm
                  title={t('mcp.toolExplorer.destructiveConfirm', {
                    defaultValue: '该工具可能产生破坏性操作，确定继续？',
                  })}
                  okText={t('common.confirm', { defaultValue: '确定' })}
                  cancelText={t('common.cancel', { defaultValue: '取消' })}
                  okButtonProps={{ danger: true }}
                  onConfirm={() => void runTool()}
                >
                  <Button type="primary" icon={<SendOutlined />} loading={loadingCall}>
                    {t('mcp.toolExplorer.runTool', { defaultValue: 'Run Tool' })}
                  </Button>
                </Popconfirm>
              ) : (
                runButton
              )}
              <Button icon={<CopyOutlined />} onClick={() => void copyInput()}>
                {t('mcp.toolExplorer.copyInput', { defaultValue: 'Copy Input' })}
              </Button>
            </Space>

            {result ? (
              <div
                className={`minerva-mcp-tool-explorer__result${
                  result.ok && !result.isError
                    ? ' minerva-mcp-tool-explorer__result--success'
                    : ' minerva-mcp-tool-explorer__result--error'
                }`}
              >
                <Space>
                  <Text strong>
                    {result.ok && !result.isError
                      ? t('mcp.toolExplorer.resultSuccess', { defaultValue: 'Tool Result: Success' })
                      : t('mcp.toolExplorer.resultError', { defaultValue: 'Tool Result: Error' })}
                  </Text>
                  <Button size="small" icon={<CopyOutlined />} onClick={() => void copyResult()}>
                    {t('mcp.toolExplorer.copyResult', { defaultValue: '复制结果' })}
                  </Button>
                </Space>
                <pre>{resultPayload}</pre>
              </div>
            ) : null}
          </>
        )}
      </main>
    </div>
  )
}
