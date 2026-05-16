/**
 * 工作区「智能体」对话页：Kimi 式布局；模型仅从已配置的模型提供商中选择，发送前拉取详情以连接上游。
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
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import {
  createAgentSession,
  deleteAgentSession,
  getAgentSessionDetail,
  listAgentSessions,
  listAgentSkills,
  streamAgentRun,
  type AgentSessionListItem,
  type AgentSkillListItem,
  type AgentStreamEvent,
} from '@/api/agent'
import {
  agentMessagesToChat,
  buildDisplayUserMessage,
  formatSessionListDate,
  sessionListLabel,
  stripSkillPrefixFromDraft,
  titleFromFirstQuestion,
} from '@/features/workspace/agentSkillUi'
import {
  deltaReasoningText,
  formatMinervaTraceLine,
  isMinervaChunkExtension,
} from '@/api/openai-stream'
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
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [draft, setDraft] = useState('')
  /** Explicitly selected skill id for the next outgoing message (from ``/`` menu). */
  const [selectedSkillId, setSelectedSkillId] = useState<string | null>(null)
  /** Highlighted row in the ``/`` skill menu (keyboard or hover). */
  const [skillHighlightIndex, setSkillHighlightIndex] = useState(0)
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

  const skillsQuery = useQuery({
    queryKey: ['agent-skills', workspaceId],
    queryFn: () => listAgentSkills(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const sessionsQuery = useQuery({
    queryKey: ['agent-sessions', workspaceId],
    queryFn: () => listAgentSessions(workspaceId!),
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

  /** Open only while picking; closes after a skill is selected (``selectedSkillId`` set). */
  const skillMenuOpen = draft.startsWith('/') && !streaming && selectedSkillId === null

  const filteredSkills = useMemo(() => {
    const list = skillsQuery.data?.skills ?? []
    if (!skillMenuOpen) return []
    const q = draft.slice(1).trim().toLowerCase()
    if (!q) return list
    return list.filter(
      (s: AgentSkillListItem) =>
        s.id.toLowerCase().includes(q) || s.description.toLowerCase().includes(q),
    )
  }, [draft, skillMenuOpen, skillsQuery.data?.skills])

  const skillItemRefs = useRef<(HTMLButtonElement | null)[]>([])

  const applySkillSelection = useCallback((s: AgentSkillListItem) => {
    setSelectedSkillId(s.id)
    setDraft(`/${s.id} `)
    window.requestAnimationFrame(() => {
      draftInputRef.current?.focus({ preventScroll: true })
    })
  }, [])

  /** Allow reopening the picker when the user edits away from the chosen ``/skill_id`` prefix. */
  useEffect(() => {
    if (!selectedSkillId) return
    const prefix = `/${selectedSkillId}`
    if (!draft.startsWith(prefix)) {
      setSelectedSkillId(null)
    }
  }, [draft, selectedSkillId])

  useEffect(() => {
    if (!skillMenuOpen) return
    setSkillHighlightIndex(0)
  }, [skillMenuOpen, filteredSkills])

  useEffect(() => {
    if (skillHighlightIndex >= filteredSkills.length && filteredSkills.length > 0) {
      setSkillHighlightIndex(filteredSkills.length - 1)
    }
  }, [filteredSkills.length, skillHighlightIndex])

  useEffect(() => {
    skillItemRefs.current[skillHighlightIndex]?.scrollIntoView({ block: 'nearest' })
  }, [skillHighlightIndex, filteredSkills])

  const handleDraftKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (!skillMenuOpen || filteredSkills.length === 0) return

      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSkillHighlightIndex((i) => (i + 1) % filteredSkills.length)
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSkillHighlightIndex((i) => (i - 1 + filteredSkills.length) % filteredSkills.length)
        return
      }
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        const picked = filteredSkills[skillHighlightIndex]
        if (picked) applySkillSelection(picked)
      }
    },
    [skillMenuOpen, filteredSkills, skillHighlightIndex, applySkillSelection],
  )

  const canSend = useMemo(() => {
    if (!workspaceId || streaming) return false
    if (!prefs.selectedModelId) return false
    const apiBody = stripSkillPrefixFromDraft(draft, selectedSkillId)
    return apiBody.length > 0 || Boolean(selectedSkillId)
  }, [workspaceId, streaming, prefs.selectedModelId, draft, selectedSkillId])

  const handleNewChat = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setSessionId(null)
    setMessages([])
    setTraceOpenKeys([])
    setStreaming(false)
    setSelectedSkillId(null)
    antdMessage.info(t('agents.newChatHint'))
  }, [t])

  const loadSession = useCallback(
    async (id: string) => {
      if (!workspaceId || streaming) return
      if (id === sessionId) return
      abortRef.current?.abort()
      abortRef.current = null
      setStreaming(false)
      setTraceOpenKeys([])
      setSelectedSkillId(null)
      setDraft('')
      try {
        const detail = await getAgentSessionDetail(workspaceId, id)
        setSessionId(detail.session.id)
        setMessages(agentMessagesToChat(detail.messages))
      } catch (e) {
        if (e instanceof ApiError) antdMessage.error(e.message)
        else antdMessage.error(String(e))
      }
    },
    [workspaceId, streaming, sessionId],
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
    const skillIdForRun = selectedSkillId
    const apiBody = stripSkillPrefixFromDraft(draft, skillIdForRun)
    const displayContent = buildDisplayUserMessage(apiBody, skillIdForRun)
    if (!apiBody && !skillIdForRun) return

    const userMsg: ChatMsg = { id: `u-${Date.now()}`, role: 'user', content: displayContent }
    const asstId = `a-${Date.now()}`
    const asstMsg: ChatMsg = { id: asstId, role: 'assistant', content: '', reasoning: '' }
    setDraft('')
    setSelectedSkillId(null)
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
        const sessionTitle = titleFromFirstQuestion(apiBody || displayContent)
        const s = await createAgentSession(
          workspaceId,
          sessionTitle ? { title: sessionTitle } : {},
        )
        sid = s.id
        setSessionId(sid)
        pushAsstLog(`[session] ${sid}`)
        void queryClient.invalidateQueries({ queryKey: ['agent-sessions', workspaceId] })
      }

      const maxTok =
        detail.max_tokens_to_sample != null && Number.isFinite(detail.max_tokens_to_sample)
          ? detail.max_tokens_to_sample
          : null

      const pk = mapProviderKind(detail.model_type)

      const { runId } = await streamAgentRun(
        workspaceId,
        sid,
        {
          user_message: apiBody || displayContent,
          skill_ids: skillIdForRun ? [skillIdForRun] : [],
          provider_kind: pk,
          base_url: baseUrl,
          api_key: apiKey,
          model: String(detail.model_name ?? '').trim(),
          temperature: null,
          max_tokens: maxTok,
        },
        (evt: AgentStreamEvent) => {
          if (evt.kind === 'done') return
          if (evt.kind === 'error') {
            const code = evt.error.code ?? 'error'
            const msg = evt.error.message ?? ''
            pushAsstLog(`[error] ${code}: ${msg}`)
            antdMessage.error(msg || code)
            return
          }
          const chunk = evt.chunk
          const minerva = chunk.minerva
          if (minerva && isMinervaChunkExtension(minerva)) {
            pushAsstLog(formatMinervaTraceLine(minerva))
            return
          }
          const choice = chunk.choices?.[0]
          const delta = choice?.delta
          if (!delta) return
          const reasoningPiece = deltaReasoningText(delta)
          if (reasoningPiece.length > 0) {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === asstId
                  ? { ...m, reasoning: (m.reasoning ?? '') + reasoningPiece }
                  : m,
              ),
            )
          }
          const contentPiece = typeof delta.content === 'string' ? delta.content : ''
          if (contentPiece.length > 0) {
            setTraceOpenKeys([])
            setMessages((prev) =>
              prev.map((m) =>
                m.id === asstId ? { ...m, content: m.content + contentPiece } : m,
              ),
            )
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
    selectedSkillId,
    prefs.selectedModelId,
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

  const showHero =
    Boolean(workspaceId) &&
    !modelsQuery.isLoading &&
    usableModels.length > 0 &&
    messages.length === 0

  return (
    <div className="agents-page">
      <aside className="agents-page__sider">
        <Button type="primary" block onClick={handleNewChat}>
          {t('agents.newChat')}
        </Button>
        <div className="agents-page__sider-history minerva-scrollbar-styled">
          <Text type="secondary" className="agents-page__sider-history-title">
            {t('agents.recentChats')}
          </Text>
          {sessionsQuery.isLoading ? (
            <Flex justify="center" style={{ padding: '12px 0' }}>
              <Spin size="small" />
            </Flex>
          ) : (sessionsQuery.data?.sessions ?? []).length === 0 ? (
            <Text type="secondary" className="agents-page__sider-history-empty">
              {t('agents.noRecentChats')}
            </Text>
          ) : (
            <div className="agents-page__sider-history-list">
              {(sessionsQuery.data?.sessions ?? []).map((s: AgentSessionListItem) => {
                const active = sessionId === s.id
                return (
                  <div
                    key={s.id}
                    className={
                      active
                        ? 'agents-page__session-row agents-page__session-row--active'
                        : 'agents-page__session-row'
                    }
                  >
                    <button
                      type="button"
                      className="agents-page__session-item"
                      onClick={() => void loadSession(s.id)}
                      disabled={streaming}
                    >
                      <span className="agents-page__session-item-title">
                        {sessionListLabel(s, t('agents.defaultSessionTitle'))}
                      </span>
                      <span className="agents-page__session-item-time">
                        {formatSessionTime(s.updated_at ?? s.created_at)}
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
            {skillMenuOpen ? (
              <div className="agents-page__skill-menu" role="listbox" aria-label={t('agents.skillPickerTitle')}>
                <Text type="secondary" className="agents-page__skill-menu-title">
                  {t('agents.skillPickerTitle')}
                </Text>
                {skillsQuery.isLoading ? (
                  <Text type="secondary" style={{ fontSize: 12, textAlign: 'left' }}>
                    {t('agents.skillLoading')}
                  </Text>
                ) : filteredSkills.length === 0 ? (
                  <Text type="secondary" style={{ fontSize: 12, textAlign: 'left' }}>
                    {t('agents.skillPickerEmpty')}
                  </Text>
                ) : (
                  <div className="agents-page__skill-menu-list">
                    {filteredSkills.map((s, idx) => (
                      <button
                        key={s.id}
                        type="button"
                        role="option"
                        aria-selected={idx === skillHighlightIndex}
                        ref={(el) => {
                          skillItemRefs.current[idx] = el
                        }}
                        className={
                          idx === skillHighlightIndex
                            ? 'agents-page__skill-item agents-page__skill-item--active'
                            : 'agents-page__skill-item'
                        }
                        onMouseEnter={() => setSkillHighlightIndex(idx)}
                        onClick={() => applySkillSelection(s)}
                      >
                        <span className="agents-page__skill-item-id">/{s.id}</span>
                        <span className="agents-page__skill-item-desc">{s.description}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : null}
            <Input.TextArea
              ref={draftInputRef}
              allowClear
              variant="borderless"
              autoSize={{ minRows: 2, maxRows: 8 }}
              value={draft}
              onChange={(e) => {
                const v = e.target.value
                setDraft(v)
                if (selectedSkillId && !v.startsWith(`/${selectedSkillId}`)) {
                  setSelectedSkillId(null)
                }
              }}
              onKeyDown={handleDraftKeyDown}
              onPressEnter={(e) => {
                if (!e.shiftKey) {
                  if (skillMenuOpen && filteredSkills.length > 0) return
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
