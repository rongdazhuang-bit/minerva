/**
 * 工作区「智能体」对话页：Kimi 式布局；模型仅从已配置的模型提供商中选择，发送前拉取详情以连接上游。
 */
import { CopyOutlined, RobotOutlined, SendOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Collapse,
  Flex,
  Input,
  Select,
  Spin,
  Typography,
  message as antdMessage,
  type InputRef,
} from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { createAgentSession, streamAgentRun, type AgentSseEvent } from '@/api/agent'
import { ApiError } from '@/api/client'
import { getModelProvider, listModelProviders, type ModelProviderListItem } from '@/api/modelProviders'
import { useAuth } from '@/app/AuthContext'
import { AgentAssistantMarkdown } from '@/features/workspace/AgentAssistantMarkdown'
import './AgentsPage.css'

const { Text, Title } = Typography

const UI_PREFS_KEY = 'minerva-agent-ui-v2'

type UiPrefs = {
  selectedModelId: string | null
}

function loadPrefs(): UiPrefs {
  try {
    const raw = sessionStorage.getItem(UI_PREFS_KEY)
    if (!raw) throw new Error('empty')
    const j = JSON.parse(raw) as Partial<UiPrefs>
    return {
      selectedModelId: typeof j.selectedModelId === 'string' ? j.selectedModelId : null,
    }
  } catch {
    return { selectedModelId: null }
  }
}

function savePrefs(p: UiPrefs) {
  sessionStorage.setItem(UI_PREFS_KEY, JSON.stringify(p))
}

/** 将后台 ``model_type`` 粗映射为 Agent run 的 ``provider_kind``。 */
function mapProviderKind(modelType: string): 'openai_compatible' | 'volcengine' | 'aliyun' {
  const s = modelType.toLowerCase()
  if (s.includes('volc') || s.includes('doubao') || s.includes('火山')) return 'volcengine'
  if (s.includes('ali') || s.includes('dashscope') || s.includes('阿里')) return 'aliyun'
  return 'openai_compatible'
}

type ChatMsg = {
  id: string
  role: 'user' | 'assistant'
  content: string
  /** 助手气泡内：运行/工具/日志等可追溯行 */
  processLog?: string[]
}

/** 工作区智能体对话主界面（类 Kimi：侧栏 + 主区 + 底部合成器，右侧选模型）。 */
export function AgentsPage() {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const [prefs, setPrefs] = useState<UiPrefs>(() => loadPrefs())
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [draft, setDraft] = useState('')
  const [streaming, setStreaming] = useState(false)
  /** 当前轮助手气泡内「运行/思考」折叠：有正文输出后自动收起 */
  const [traceOpenKeys, setTraceOpenKeys] = useState<string[]>([])
  const abortRef = useRef<AbortController | null>(null)
  const listEndRef = useRef<HTMLDivElement | null>(null)
  /** Composer ``Input.TextArea`` ref for refocus after a run finishes. */
  const draftInputRef = useRef<InputRef | null>(null)
  /** Tracks previous ``streaming`` to detect assistant run completion. */
  const wasStreamingRef = useRef(false)

  const modelsQuery = useQuery({
    queryKey: ['agent-model-providers', workspaceId],
    queryFn: () => listModelProviders(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const usableModels = useMemo(() => {
    const rows = modelsQuery.data ?? []
    return rows.filter(
      (m: ModelProviderListItem) =>
        m.enabled && Boolean(m.endpoint_url?.trim()) && m.has_api_key,
    )
  }, [modelsQuery.data])

  useEffect(() => {
    setPrefs((p) => {
      if (p.selectedModelId) return p
      if (usableModels.length === 0) return p
      const next = { ...p, selectedModelId: usableModels[0]!.id }
      savePrefs(next)
      return next
    })
  }, [usableModels])

  const setSelectedModelId = useCallback((id: string | null) => {
    setPrefs((p) => {
      const next = { ...p, selectedModelId: id }
      savePrefs(next)
      return next
    })
  }, [])

  /** 将单条消息正文写入剪贴板（助手为原始 Markdown）。 */
  const copyMessageBody = useCallback(
    async (text: string) => {
      try {
        await navigator.clipboard.writeText(text)
        antdMessage.success(t('agents.copySuccess'))
      } catch {
        antdMessage.error(t('agents.copyFailed'))
      }
    },
    [t],
  )

  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streaming])

  /** When assistant streaming ends, focus the draft field so the user can type the next message. */
  useEffect(() => {
    if (wasStreamingRef.current && !streaming) {
      const id = window.requestAnimationFrame(() => {
        draftInputRef.current?.focus({ preventScroll: true })
      })
      wasStreamingRef.current = streaming
      return () => window.cancelAnimationFrame(id)
    }
    wasStreamingRef.current = streaming
  }, [streaming])

  const canSend = useMemo(() => {
    if (!workspaceId || streaming) return false
    if (!prefs.selectedModelId) return false
    return draft.trim().length > 0
  }, [workspaceId, streaming, prefs.selectedModelId, draft])

  const handleNewChat = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setSessionId(null)
    setMessages([])
    setTraceOpenKeys([])
    setStreaming(false)
    antdMessage.info(t('agents.newChatHint'))
  }, [t])

  const onSend = useCallback(async () => {
    if (!workspaceId) {
      antdMessage.error(t('agents.noWorkspace'))
      return
    }
    const mid = prefs.selectedModelId
    if (!mid) {
      antdMessage.warning(t('agents.pickModel'))
      return
    }
    const text = draft.trim()
    if (!text) return

    const userMsg: ChatMsg = { id: `u-${Date.now()}`, role: 'user', content: text }
    const asstId = `a-${Date.now()}`
    const asstMsg: ChatMsg = { id: asstId, role: 'assistant', content: '' }
    setDraft('')
    setMessages((m) => [...m, userMsg, asstMsg])
    setStreaming(true)
    setTraceOpenKeys(['trace'])

    const ac = new AbortController()
    abortRef.current = ac

    const pushAsstLog = (line: string) => {
      setMessages((prev) =>
        prev.map((row) =>
          row.id === asstId && row.role === 'assistant'
            ? { ...row, processLog: [...(row.processLog ?? []).slice(-199), line] }
            : row,
        ),
      )
    }

    let sid = sessionId
    try {
      const detail = await getModelProvider(workspaceId, mid)
      const baseUrl = (detail.endpoint_url ?? '').trim()
      const apiKey = (detail.api_key ?? '').trim()
      if (!baseUrl || !apiKey) {
        throw new ApiError('agent.model_incomplete', t('agents.modelMissingSecret'))
      }

      if (!sid) {
        const s = await createAgentSession(workspaceId, { title: t('agents.defaultSessionTitle') })
        sid = s.id
        setSessionId(sid)
        pushAsstLog(`[session] ${sid}`)
      }

      const maxTok =
        detail.max_tokens_to_sample != null && Number.isFinite(detail.max_tokens_to_sample)
          ? detail.max_tokens_to_sample
          : null

      const pk = mapProviderKind(detail.model_type)

      await streamAgentRun(
        workspaceId,
        sid,
        {
          user_message: text,
          skill_ids: [],
          provider_kind: pk,
          base_url: baseUrl,
          api_key: apiKey,
          model: String(detail.model_name ?? '').trim(),
          temperature: null,
          max_tokens: maxTok,
        },
        (evt: AgentSseEvent) => {
          const typ = String(evt.type)
          if (typ === 'run_started') {
            pushAsstLog(`[run_started] ${evt.run_id}`)
            return
          }
          if (typ === 'assistant_delta' && typeof evt.text === 'string') {
            const chunk = evt.text
            if (chunk.length > 0) {
              setTraceOpenKeys([])
            }
            setMessages((prev) =>
              prev.map((m) =>
                m.id === asstId ? { ...m, content: m.content + chunk } : m,
              ),
            )
            return
          }
          if (typ === 'log' || typ === 'step') {
            const body = typeof evt.message === 'string' ? evt.message : JSON.stringify(evt)
            pushAsstLog(`[${typ}] ${body}`)
            return
          }
          if (typ === 'tool_start' || typ === 'tool_result') {
            pushAsstLog(`[${typ}] ${JSON.stringify(evt)}`)
            return
          }
          if (typ === 'error') {
            const code = typeof evt.code === 'string' ? evt.code : 'error'
            const msg = typeof evt.message === 'string' ? evt.message : ''
            pushAsstLog(`[error] ${code}: ${msg}`)
            antdMessage.error(msg || code)
            return
          }
          if (typ === 'run_finished') {
            pushAsstLog(`[run_finished] ${String(evt.status ?? '')}`)
          }
        },
        ac.signal,
      )
    } catch (e) {
      if ((e as Error).name === 'AbortError') {
        pushAsstLog('[aborted]')
      } else if (e instanceof ApiError) {
        antdMessage.error(e.message)
        pushAsstLog(`[api] ${e.code}: ${e.message}`)
      } else {
        antdMessage.error(String(e))
        pushAsstLog(`[error] ${String(e)}`)
      }
    } finally {
      setStreaming(false)
      abortRef.current = null
    }
  }, [
    workspaceId,
    sessionId,
    draft,
    prefs.selectedModelId,
    t,
  ])

  const selectOptions = useMemo(
    () =>
      usableModels.map((m) => ({
        value: m.id,
        label: `${m.provider_name} · ${m.model_name}`,
        title: m.endpoint_url ?? undefined,
      })),
    [usableModels],
  )

  const lastMessageId = useMemo(() => messages[messages.length - 1]?.id, [messages])

  const assistantTraceBelowRobot = useCallback(
    (m: ChatMsg) => {
      if (m.role !== 'assistant') return null
      const logs = m.processLog ?? []
      const isLatestAssistantCard = m.id === lastMessageId
      const showTrace = (streaming && isLatestAssistantCard) || logs.length > 0
      if (!showTrace) return null
      return (
        <Collapse
          className="agents-page__trace"
          size="small"
          ghost
          bordered={false}
          expandIconPosition="start"
          style={{ marginTop: 6, marginBottom: 4 }}
          items={[
            {
              key: 'trace',
              label: <span style={{ fontSize: 12 }}>{t('agents.assistantTrace')}</span>,
              children: (
                <div className="agents-page__process">
                  {logs.length === 0 ? (
                    <Text type="secondary">{t('agents.processEmpty')}</Text>
                  ) : (
                    logs.map((line, i) => (
                      <div key={`${m.id}-${i}-${line.slice(0, 48)}`}>{line}</div>
                    ))
                  )}
                </div>
              ),
            },
          ]}
          {...(isLatestAssistantCard
            ? {
                activeKey: traceOpenKeys,
                onChange: (k: string | string[]) =>
                  setTraceOpenKeys(Array.isArray(k) ? k : k ? [k] : []),
              }
            : { defaultActiveKey: [] as string[] })}
        />
      )
    },
    [lastMessageId, streaming, traceOpenKeys, t],
  )

  return (
    <div className="agents-page">
      <aside className="agents-page__sider">
        <Button type="primary" block onClick={handleNewChat}>
          {t('agents.newChat')}
        </Button>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {t('agents.sidebarHint')}
        </Text>
      </aside>

      <div className="agents-page__main">
        <div className="agents-page__scroll minerva-scrollbar-styled">
          {!workspaceId ? (
            <Alert type="warning" message={t('agents.noWorkspace')} showIcon />
          ) : modelsQuery.isLoading ? (
            <Flex align="center" justify="center" style={{ minHeight: 200 }}>
              <Spin />
            </Flex>
          ) : usableModels.length === 0 ? (
            <Alert
              type="info"
              showIcon
              message={t('agents.noModelsConfigured')}
              description={
                <span>
                  {t('agents.noModelsConfiguredHint')}{' '}
                  <Link to="/app/settings/models">{t('agents.openModelSettings')}</Link>
                  {t('agents.noModelsConfiguredHintSuffix')}
                </span>
              }
            />
          ) : messages.length === 0 ? (
            <div className="agents-page__hero">
              <RobotOutlined style={{ fontSize: 48, opacity: 0.35 }} />
              <Title level={2} className="agents-page__hero-title">
                {t('agents.heroTitle')}
              </Title>
              <Text type="secondary">{t('agents.heroHint')}</Text>
            </div>
          ) : (
            messages.map((m) => (
              <div
                key={m.id}
                style={{
                  display: 'flex',
                  justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start',
                  marginBottom: 12,
                }}
              >
                <div className="agents-page__msg">
                  <div
                    style={{
                      marginBottom: 6,
                      textAlign: m.role === 'user' ? 'right' : 'left',
                    }}
                  >
                    {m.role === 'user' ? (
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {t('agents.roleUser')}
                      </Text>
                    ) : (
                      <RobotOutlined
                        aria-label={t('agents.roleAssistant')}
                        title={t('agents.roleAssistant')}
                        style={{
                          fontSize: 13,
                          color: 'var(--minerva-ink-muted, #a8b8cc)',
                        }}
                      />
                    )}
                  </div>
                  {assistantTraceBelowRobot(m)}
                  <Flex align="flex-start" gap={8}>
                    {streaming && m.role === 'assistant' && !m.content ? (
                      <Spin size="small" style={{ marginTop: 4 }} />
                    ) : null}
                    {m.role === 'assistant' ? (
                      <div style={{ flex: 1, minWidth: 0, textAlign: 'left' }}>
                        <AgentAssistantMarkdown markdown={m.content} />
                      </div>
                    ) : (
                      <div className="agents-page__md-user-wrap" style={{ flex: 1, minWidth: 0 }}>
                        <AgentAssistantMarkdown markdown={m.content} />
                      </div>
                    )}
                  </Flex>
                  {(m.content ?? '').trim().length > 0 ? (
                    <div
                      className="agents-page__msg-copy"
                      style={{
                        display: 'flex',
                        justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start',
                      }}
                    >
                      <Button
                        type="text"
                        size="small"
                        className="agents-page__msg-copy-btn"
                        icon={<CopyOutlined />}
                        aria-label={t('agents.copyMessage')}
                        title={t('agents.copyMessage')}
                        onClick={() => void copyMessageBody(m.content)}
                      />
                    </div>
                  ) : null}
                </div>
              </div>
            ))
          )}
          <div ref={listEndRef} />
        </div>

        <div className="agents-page__composer-wrap">
          <div className="agents-page__composer">
            <Input.TextArea
              ref={draftInputRef}
              allowClear
              variant="borderless"
              autoSize={{ minRows: 2, maxRows: 8 }}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onPressEnter={(e) => {
                if (!e.shiftKey) {
                  e.preventDefault()
                  if (canSend) void onSend()
                }
              }}
              placeholder={t('agents.inputPlaceholderKimi')}
              disabled={!workspaceId || streaming || usableModels.length === 0}
            />
            <div className="agents-page__composer-footer">
              <Flex
                align="center"
                gap={10}
                style={{ flex: 1, minWidth: 0, width: '100%', justifyContent: 'flex-end' }}
              >
                <Select
                  showSearch
                  optionFilterProp="label"
                  placeholder={t('agents.pickModel')}
                  style={{ minWidth: 220, maxWidth: 360 }}
                  value={prefs.selectedModelId ?? undefined}
                  onChange={(v) => setSelectedModelId(v)}
                  disabled={streaming || usableModels.length === 0}
                  loading={modelsQuery.isFetching}
                  options={selectOptions}
                />
                <Button
                  type="primary"
                  shape="circle"
                  icon={<SendOutlined />}
                  loading={streaming}
                  disabled={!canSend}
                  onClick={() => void onSend()}
                />
              </Flex>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
