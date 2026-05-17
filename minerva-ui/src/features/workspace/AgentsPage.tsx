/**
 * 工作区「智能体」对话页：Kimi 式布局；模型仅从已配置的模型提供商列表中选择（运行由后端按 model_id 加载）。
 */
import { CopyOutlined, MoreOutlined, RobotOutlined, SendOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Collapse,
  Dropdown,
  Flex,
  Input,
  Modal,
  Select,
  Spin,
  Typography,
  message as antdMessage,
  type InputRef,
  type MenuProps,
} from 'antd'
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import {
  createAgentSession,
  deleteAgentSession,
  getAgentSessionDetail,
  AGENT_SESSIONS_PAGE_SIZE,
  listAgentSessions,
  streamAgentRun,
  type AgentSessionListItem,
  type AgentStreamEvent,
} from '@/api/agent'
import { formatAgentV2TraceLine } from '@/api/agent-stream-v2'
import {
  agentMessagesToChat,
  formatSessionListDate,
  sessionListLabel,
  titleFromFirstQuestion,
} from '@/features/workspace/agentSkillUi'
import { ApiError } from '@/api/client'
import { listModelProviders, type ModelProviderListItem } from '@/api/modelProviders'
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

type ChatMsg = {
  id: string
  role: 'user' | 'assistant'
  content: string
  /** 模型推理 token 流（与正文分离展示） */
  reasoning?: string
  /** 助手气泡内：编排轨迹（minerva 事件） */
  processLog?: string[]
}

/** 工作区智能体对话主界面（类 Kimi：侧栏 + 主区 + 底部合成器，右侧选模型）。 */
export function AgentsPage() {
  const { t, i18n } = useTranslation()
  const queryClient = useQueryClient()
  const { workspaceId } = useAuth()
  const [prefs, setPrefs] = useState<UiPrefs>(() => loadPrefs())
  const [sessionId, setSessionId] = useState<string | null>(null)
  /** Session id being loaded after a sidebar click (detail fetch in flight). */
  const [sessionLoadingId, setSessionLoadingId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [draft, setDraft] = useState('')
  const [streaming, setStreaming] = useState(false)
  /** 当前轮助手气泡内「运行/思考」折叠：有正文输出后自动收起 */
  const [traceOpenKeys, setTraceOpenKeys] = useState<string[]>([])
  const abortRef = useRef<AbortController | null>(null)
  const listEndRef = useRef<HTMLDivElement | null>(null)
  /** Sidebar history list scroll container (infinite session pagination). */
  const historyScrollRef = useRef<HTMLDivElement | null>(null)
  /** Sentinel at list bottom for IntersectionObserver-based pagination. */
  const historyLoadMoreRef = useRef<HTMLDivElement | null>(null)
  /** Composer ``Input.TextArea`` ref for refocus after a run finishes. */
  const draftInputRef = useRef<InputRef | null>(null)
  /** Tracks previous ``streaming`` to detect assistant run completion. */
  const wasStreamingRef = useRef(false)

  const modelsQuery = useQuery({
    queryKey: ['agent-model-providers', workspaceId],
    queryFn: () => listModelProviders(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const sessionsQuery = useInfiniteQuery({
    queryKey: ['agent-sessions', workspaceId],
    queryFn: ({ pageParam }) =>
      listAgentSessions(workspaceId!, {
        limit: AGENT_SESSIONS_PAGE_SIZE,
        cursor: pageParam ?? undefined,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => (last.has_more ? last.next_cursor : undefined),
    enabled: Boolean(workspaceId),
  })

  const sessionList = useMemo(
    () => sessionsQuery.data?.pages.flatMap((page) => page.sessions) ?? [],
    [sessionsQuery.data],
  )

  const {
    hasNextPage: sessionsHasNextPage,
    isFetchingNextPage: sessionsFetchingNextPage,
    fetchNextPage: fetchNextSessionsPage,
    isSuccess: sessionsLoaded,
  } = sessionsQuery

  const maybeLoadMoreSessions = useCallback(() => {
    const el = historyScrollRef.current
    if (!el || !sessionsHasNextPage || sessionsFetchingNextPage) {
      return
    }
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 56) {
      void fetchNextSessionsPage()
    }
  }, [sessionsHasNextPage, sessionsFetchingNextPage, fetchNextSessionsPage])

  const handleHistoryScroll = useCallback(() => {
    maybeLoadMoreSessions()
  }, [maybeLoadMoreSessions])

  /** Keep wheel inside history scroller; load more when already at bottom. */
  const handleHistoryWheel = useCallback(
    (e: React.WheelEvent<HTMLDivElement>) => {
      const el = historyScrollRef.current
      if (!el) {
        return
      }
      const canScrollInside = el.scrollHeight > el.clientHeight + 1
      const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 1
      const atTop = el.scrollTop <= 0
      const scrollingDown = e.deltaY > 0
      const scrollingUp = e.deltaY < 0

      if (canScrollInside) {
        if ((scrollingDown && !atBottom) || (scrollingUp && !atTop)) {
          e.stopPropagation()
          return
        }
        if (scrollingDown && atBottom) {
          e.stopPropagation()
          maybeLoadMoreSessions()
        }
        return
      }

      if (scrollingDown && sessionsHasNextPage) {
        e.stopPropagation()
        maybeLoadMoreSessions()
      }
    },
    [maybeLoadMoreSessions, sessionsHasNextPage],
  )

  useEffect(() => {
    if (!sessionsLoaded || !sessionsHasNextPage || sessionsFetchingNextPage) {
      return
    }
    const el = historyScrollRef.current
    if (!el || el.scrollHeight > el.clientHeight + 8) {
      return
    }
    void fetchNextSessionsPage()
  }, [
    sessionList.length,
    sessionsLoaded,
    sessionsHasNextPage,
    sessionsFetchingNextPage,
    fetchNextSessionsPage,
  ])

  useEffect(() => {
    const root = historyScrollRef.current
    const sentinel = historyLoadMoreRef.current
    if (!root || !sentinel || !sessionsHasNextPage) {
      return
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          maybeLoadMoreSessions()
        }
      },
      { root, rootMargin: '64px', threshold: 0 },
    )
    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [sessionList.length, sessionsHasNextPage, maybeLoadMoreSessions])

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
    setSessionLoadingId(null)
    setMessages([])
    setTraceOpenKeys([])
    setStreaming(false)
    antdMessage.info(t('agents.newChatHint'))
  }, [t])

  const loadSession = useCallback(
    async (id: string) => {
      if (!workspaceId || streaming) return
      if (id === sessionId && !sessionLoadingId) return
      abortRef.current?.abort()
      abortRef.current = null
      setStreaming(false)
      setTraceOpenKeys([])
      setDraft('')
      setSessionLoadingId(id)
      setMessages([])
      try {
        const detail = await getAgentSessionDetail(workspaceId, id)
        setSessionId(detail.session.id)
        setMessages(agentMessagesToChat(detail.messages))
      } catch (e) {
        if (e instanceof ApiError) antdMessage.error(e.message)
        else antdMessage.error(String(e))
      } finally {
        setSessionLoadingId(null)
      }
    },
    [workspaceId, streaming, sessionId, sessionLoadingId],
  )

  const formatSessionTime = useCallback(
    (iso: string | null | undefined) => formatSessionListDate(iso, i18n.language),
    [i18n.language],
  )

  const handleDeleteSession = useCallback(
    async (targetSessionId: string) => {
      if (!workspaceId) return
      if (streaming) {
        antdMessage.warning(t('agents.deleteSessionWhileStreaming'))
        return
      }
      try {
        await deleteAgentSession(workspaceId, targetSessionId)
        antdMessage.success(t('agents.deleteSessionSuccess'))
        if (sessionId === targetSessionId) {
          handleNewChat()
        }
        void queryClient.invalidateQueries({ queryKey: ['agent-sessions', workspaceId] })
      } catch (e) {
        if (e instanceof ApiError) antdMessage.error(e.message)
        else antdMessage.error(String(e))
      }
    },
    [workspaceId, sessionId, streaming, handleNewChat, queryClient, t],
  )

  const confirmDeleteSession = useCallback(
    (targetSessionId: string) => {
      Modal.confirm({
        title: t('agents.deleteSessionConfirm'),
        okText: t('agents.deleteSession'),
        okButtonProps: { danger: true },
        cancelText: t('common.cancel'),
        onOk: () => handleDeleteSession(targetSessionId),
      })
    },
    [t, handleDeleteSession],
  )

  const buildSessionRowMenu = useCallback(
    (targetSessionId: string): MenuProps => ({
      items: [
        {
          key: 'delete',
          label: t('agents.deleteSession'),
          danger: true,
          onClick: ({ domEvent }) => {
            domEvent.stopPropagation()
            confirmDeleteSession(targetSessionId)
          },
        },
      ],
    }),
    [t, confirmDeleteSession],
  )

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
    const apiBody = draft.trim()
    if (!apiBody) return

    const userMsg: ChatMsg = { id: `u-${Date.now()}`, role: 'user', content: apiBody }
    const asstId = `a-${Date.now()}`
    const asstMsg: ChatMsg = { id: asstId, role: 'assistant', content: '', reasoning: '' }
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
      const modelRow = usableModels.find((m) => m.id === mid)
      const maxTok =
        modelRow?.max_tokens_to_sample != null &&
        Number.isFinite(modelRow.max_tokens_to_sample)
          ? modelRow.max_tokens_to_sample
          : null

      if (!sid) {
        const sessionTitle = titleFromFirstQuestion(apiBody)
        const s = await createAgentSession(
          workspaceId,
          sessionTitle ? { title: sessionTitle } : {},
        )
        sid = s.id
        setSessionId(sid)
        pushAsstLog(`[session] ${sid}`)
        void queryClient.invalidateQueries({ queryKey: ['agent-sessions', workspaceId] })
      }

      const { runId } = await streamAgentRun(
        workspaceId,
        sid,
        {
          user_message: apiBody,
          model_id: mid,
          temperature: null,
          max_tokens: maxTok,
          preferred_skills: [],
        },
        (evt: AgentStreamEvent) => {
          if (evt.kind === 'done') return
          if (evt.kind === 'error') {
            pushAsstLog(`[error] ${evt.code}: ${evt.message}`)
            antdMessage.error(evt.message || evt.code)
            return
          }
          const ev = evt.event
          const traceLine = formatAgentV2TraceLine(ev)
          if (traceLine) pushAsstLog(traceLine)
          if (ev.type === 'llm.delta') {
            const channel = String(ev.payload.channel ?? 'assistant')
            const text = String(ev.payload.text ?? '')
            if (!text) return
            if (channel === 'reasoning') {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === asstId ? { ...m, reasoning: (m.reasoning ?? '') + text } : m,
                ),
              )
            } else {
              setTraceOpenKeys([])
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === asstId ? { ...m, content: m.content + text } : m,
                ),
              )
            }
            return
          }
        },
        ac.signal,
      )
      if (runId) {
        pushAsstLog(`[run] ${runId}`)
      }
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
      void queryClient.invalidateQueries({ queryKey: ['agent-sessions', workspaceId] })
    }
  }, [
    workspaceId,
    sessionId,
    draft,
    prefs.selectedModelId,
    usableModels,
    queryClient,
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

  const assistantReasoningBelowRobot = useCallback(
    (m: ChatMsg) => {
      if (m.role !== 'assistant') return null
      const text = (m.reasoning ?? '').trim()
      if (!text) return null
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
              key: 'reasoning',
              label: <span style={{ fontSize: 12 }}>{t('agents.modelReasoning')}</span>,
              children: <div className="agents-page__process">{text}</div>,
            },
          ]}
          defaultActiveKey={[]}
        />
      )
    },
    [t],
  )

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

  const sessionDetailLoading = sessionLoadingId !== null

  const showHero =
    Boolean(workspaceId) &&
    !modelsQuery.isLoading &&
    usableModels.length > 0 &&
    !sessionDetailLoading &&
    messages.length === 0

  return (
    <div className="agents-page">
      <aside className="agents-page__sider">
        <Button type="primary" block onClick={handleNewChat}>
          {t('agents.newChat')}
        </Button>
        <div
          ref={historyScrollRef}
          className="agents-page__sider-history minerva-scrollbar-styled"
          onScroll={handleHistoryScroll}
          onWheel={handleHistoryWheel}
        >
          <Text type="secondary" className="agents-page__sider-history-title">
            {t('agents.recentChats')}
          </Text>
          {sessionsQuery.isLoading ? (
            <Flex justify="center" style={{ padding: '12px 0' }}>
              <Spin size="small" />
            </Flex>
          ) : sessionList.length === 0 ? (
            <Text type="secondary" className="agents-page__sider-history-empty">
              {t('agents.noRecentChats')}
            </Text>
          ) : (
            <div className="agents-page__sider-history-list">
              {sessionList.map((s: AgentSessionListItem) => {
                const active = sessionId === s.id
                const loading = sessionLoadingId === s.id
                return (
                  <div
                    key={s.id}
                    className={
                      active || loading
                        ? 'agents-page__session-row agents-page__session-row--active'
                        : 'agents-page__session-row'
                    }
                  >
                    <button
                      type="button"
                      className="agents-page__session-item"
                      onClick={() => void loadSession(s.id)}
                      disabled={streaming || sessionDetailLoading}
                    >
                      <span className="agents-page__session-item-title">
                        {sessionListLabel(s, t('agents.defaultSessionTitle'))}
                      </span>
                      <span className="agents-page__session-item-time">
                        {loading ? (
                          <Spin size="small" />
                        ) : (
                          formatSessionTime(s.updated_at ?? s.created_at)
                        )}
                      </span>
                    </button>
                    <Dropdown menu={buildSessionRowMenu(s.id)} trigger={['click']}>
                      <Button
                        type="text"
                        size="small"
                        className="agents-page__session-item-menu"
                        icon={<MoreOutlined />}
                        aria-label={t('agents.sessionMenu')}
                        disabled={streaming}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </Dropdown>
                  </div>
                )
              })}
            </div>
          )}
          {sessionList.length > 0 && sessionsHasNextPage ? (
            <div
              ref={historyLoadMoreRef}
              className="agents-page__sider-history-sentinel"
              aria-hidden
            />
          ) : null}
          {sessionsQuery.isFetchingNextPage ? (
            <Flex justify="center" className="agents-page__sider-history-more">
              <Spin size="small" />
            </Flex>
          ) : null}
        </div>
      </aside>

      <div className="agents-page__main">
        <div
          className={`agents-page__scroll minerva-scrollbar-styled${showHero ? ' agents-page__scroll--hero' : ''}`}
        >
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
          ) : sessionDetailLoading ? (
            <Flex
              vertical
              align="center"
              justify="center"
              gap={12}
              className="agents-page__session-loading"
            >
              <Spin />
              <Text type="secondary">{t('agents.loadingSession')}</Text>
            </Flex>
          ) : messages.length === 0 ? (
            <div className="agents-page__hero-wrap">
              <div className="agents-page__hero">
                <RobotOutlined style={{ fontSize: 48, opacity: 0.35 }} />
                <Title level={2} className="agents-page__hero-title">
                  {t('agents.heroTitle')}
                </Title>
                <Text type="secondary" className="agents-page__hero-hint">
                  {t('agents.heroHint')}
                </Text>
              </div>
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
                  {assistantReasoningBelowRobot(m)}
                  {assistantTraceBelowRobot(m)}
                  <Flex align="flex-start" gap={8}>
                    {streaming &&
                    m.role === 'assistant' &&
                    !m.content &&
                    !(m.reasoning ?? '').trim() ? (
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
          {messages.length > 0 ? <div ref={listEndRef} /> : null}
        </div>

        <div className="agents-page__composer-wrap">
          <div className="agents-page__composer">
            <Input.TextArea
              ref={draftInputRef}
              allowClear
              variant="borderless"
              classNames={{ textarea: 'agents-page__composer-input' }}
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
