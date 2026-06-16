/**
 * 工作区「智能体」对话页：Kimi 式布局；模型仅从已配置的模型提供商列表中选择（运行由后端按 model_id 加载）。
 */
import {
  CopyOutlined,
  MoreOutlined,
  RedoOutlined,
  RobotOutlined,
  SendOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Collapse,
  Dropdown,
  Flex,
  Input,
  Popconfirm,
  Select,
  Spin,
  Typography,
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
  listAgentConversationModels,
  listAgentSessions,
  streamAgentRun,
  type AgentSessionListItem,
  type AgentStreamEvent,
} from '@/api/agent'
import { extractTotalTokens, formatAgentV2TraceLine, formatTokenCount, formatTokenNumber, extractReasoningTokens } from '@/api/agent-stream-v2'
import {
  agentMessagesToChat,
  appendReasoningDelta,
  formatReasoningSegmentLabel,
  formatSessionListDate,
  hasVisibleReasoning,
  resolveReasoningTokenCount,
  isAgentMessageUuid,
  mergeAgentChatWithLocal,
  sessionListLabel,
  titleFromFirstQuestion,
  updateReasoningSegmentTokens,
  type AgentChatMsg,
} from '@/features/agent/agentSkillUi'
import { ApiError } from '@/api/client'
import { useAuth } from '@/app/AuthContext'
import { useAppMessage } from '@/app/useAppMessage'
import { copyTextToClipboard } from '@/components/markdown/copyToClipboard'
import { AgentAssistantMarkdown } from '@/features/agent/AgentAssistantMarkdown'
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

/** 工作区智能体对话主界面（类 Kimi：侧栏 + 主区 + 底部合成器，右侧选模型）。 */
export function AgentsPage() {
  const { t, i18n } = useTranslation()
  const message = useAppMessage()
  const queryClient = useQueryClient()
  const { workspaceId } = useAuth()
  const [prefs, setPrefs] = useState<UiPrefs>(() => loadPrefs())
  const [sessionId, setSessionId] = useState<string | null>(null)
  /** Session id being loaded after a sidebar click (detail fetch in flight). */
  const [sessionLoadingId, setSessionLoadingId] = useState<string | null>(null)
  const [messages, setMessages] = useState<AgentChatMsg[]>([])
  const [draft, setDraft] = useState('')
  const [streaming, setStreaming] = useState(false)
  /** 当前轮助手气泡内「运行过程」折叠 */
  const [traceOpenKeys, setTraceOpenKeys] = useState<string[]>([])
  /** 当前轮助手气泡内「思考过程」折叠 */
  const [reasoningOpenKeys, setReasoningOpenKeys] = useState<string[]>([])
  /** 是否向服务端请求思考模式（默认关闭）。 */
  const [thinkingEnabled, setThinkingEnabled] = useState(false)
  /** 侧栏会话删除确认：Popconfirm 须挂在 Dropdown 外，避免菜单关闭时确认框被卸载。 */
  const [sessionDeleteConfirmId, setSessionDeleteConfirmId] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const listEndRef = useRef<HTMLDivElement | null>(null)
  /** Main session message list scroll container. */
  const chatScrollRef = useRef<HTMLDivElement | null>(null)
  /** Sidebar history list scroll container (infinite session pagination). */
  const historyScrollRef = useRef<HTMLDivElement | null>(null)
  /** Sentinel at list bottom for IntersectionObserver-based pagination. */
  const historyLoadMoreRef = useRef<HTMLDivElement | null>(null)
  /** Composer ``Input.TextArea`` ref for refocus after a run finishes. */
  const draftInputRef = useRef<InputRef | null>(null)
  /** Tracks previous ``streaming`` to detect assistant run completion. */
  const wasStreamingRef = useRef(false)
  /** When true, user scrolled up in the message list; pause auto-scroll until next send. */
  const userScrolledUpRef = useRef(false)

  const modelsQuery = useQuery({
    queryKey: ['agent-conversation-models', workspaceId],
    queryFn: () => listAgentConversationModels(workspaceId!),
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

  /**
   * 将问答区 Markdown 上的纵向滚轮转给主消息滚动容器。
   * 「运行过程」等内层纵向滚动区在可滚动时保留原生滚轮；须用非 passive 原生监听才能 ``preventDefault``。
   */
  const forwardMessageWheelToChat = useCallback((e: WheelEvent) => {
    const chat = chatScrollRef.current
    if (!chat || Math.abs(e.deltaY) <= Math.abs(e.deltaX)) {
      return
    }
    const target = e.target
    if (!(target instanceof HTMLElement)) {
      return
    }
    const horizontalPane = target.closest(
      '.minerva-md-table-scroll, .minerva-md-syntax, .minerva-md-pre, .minerva-md-mermaid, .minerva-md-chart',
    )
    if (horizontalPane instanceof HTMLElement && Math.abs(e.deltaX) > 0) {
      const canScrollX = horizontalPane.scrollWidth > horizontalPane.clientWidth + 1
      const atLeft = horizontalPane.scrollLeft <= 0
      const atRight =
        horizontalPane.scrollLeft + horizontalPane.clientWidth >= horizontalPane.scrollWidth - 1
      if (canScrollX && ((e.deltaX < 0 && !atLeft) || (e.deltaX > 0 && !atRight))) {
        return
      }
    }
    const processPane = target.closest('.agents-page__process')
    if (processPane instanceof HTMLElement) {
      const canScrollY = processPane.scrollHeight > processPane.clientHeight + 1
      if (canScrollY) {
        const atTop = processPane.scrollTop <= 0
        const atBottom =
          processPane.scrollTop + processPane.clientHeight >= processPane.scrollHeight - 1
        if ((e.deltaY < 0 && !atTop) || (e.deltaY > 0 && !atBottom)) {
          return
        }
      }
    }
    const maxScroll = chat.scrollHeight - chat.clientHeight
    if (maxScroll <= 0) {
      return
    }
    const prev = chat.scrollTop
    chat.scrollTop = Math.max(0, Math.min(maxScroll, prev + e.deltaY))
    if (chat.scrollTop !== prev) {
      e.preventDefault()
      e.stopPropagation()
    }
  }, [])

  useEffect(() => {
    const chat = chatScrollRef.current
    if (!chat) return
    chat.addEventListener('wheel', forwardMessageWheelToChat, { passive: false, capture: true })
    return () => chat.removeEventListener('wheel', forwardMessageWheelToChat, { capture: true })
  }, [forwardMessageWheelToChat])

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

  const usableModels = useMemo(() => modelsQuery.data ?? [], [modelsQuery.data])

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
      const ok = await copyTextToClipboard(text)
      if (ok) message.success(t('agents.copySuccess'))
      else message.error(t('agents.copyFailed'))
    },
    [t],
  )

  /** Track whether the user manually scrolled away from the bottom of the message list. */
  useEffect(() => {
    const chat = chatScrollRef.current
    if (!chat) return
    const onScroll = () => {
      const dist = chat.scrollHeight - chat.scrollTop - chat.clientHeight
      userScrolledUpRef.current = dist > 96
    }
    chat.addEventListener('scroll', onScroll, { passive: true })
    return () => chat.removeEventListener('scroll', onScroll)
  }, [])

  /** Scroll only the in-page message scroller (never ``scrollIntoView`` — avoids shifting the whole layout). */
  const scrollChatToEnd = useCallback((behavior: ScrollBehavior = 'auto') => {
    const chat = chatScrollRef.current
    if (!chat) return
    if (streaming && userScrolledUpRef.current) return
    chat.scrollTo({ top: chat.scrollHeight, behavior })
  }, [streaming])

  useEffect(() => {
    if (messages.length === 0) return
    const behavior: ScrollBehavior = streaming ? 'auto' : 'smooth'
    const id = requestAnimationFrame(() => scrollChatToEnd(behavior))
    return () => cancelAnimationFrame(id)
  }, [messages, streaming, scrollChatToEnd])

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
    setDraft('')
    setTraceOpenKeys([])
    setStreaming(false)
    userScrolledUpRef.current = false
    message.info(t('agents.newChatHint'))
    window.requestAnimationFrame(() => {
      draftInputRef.current?.focus({ preventScroll: true })
    })
  }, [t, message])

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
        if (e instanceof ApiError) message.error(e.message)
        else message.error(String(e))
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
      setSessionDeleteConfirmId(null)
      if (streaming) {
        message.warning(t('agents.deleteSessionWhileStreaming'))
        return
      }
      try {
        await deleteAgentSession(workspaceId, targetSessionId)
        message.success(t('agents.deleteSessionSuccess'))
        if (sessionId === targetSessionId) {
          handleNewChat()
        }
        void queryClient.invalidateQueries({ queryKey: ['agent-sessions', workspaceId] })
      } catch (e) {
        if (e instanceof ApiError) {
          if (e.code === 'agent.session_busy') {
            message.warning(t('agents.deleteSessionBusy'))
          } else {
            message.error(e.message)
          }
        } else message.error(String(e))
      }
    },
    [workspaceId, sessionId, streaming, handleNewChat, queryClient, t],
  )

  const buildSessionRowMenu = useCallback(
    (targetSessionId: string): MenuProps => ({
      items: [
        {
          key: 'delete',
          danger: true,
          label: t('agents.deleteSession'),
          onClick: ({ domEvent }) => {
            domEvent.stopPropagation()
            setSessionDeleteConfirmId(targetSessionId)
          },
        },
      ],
    }),
    [t],
  )

  /** 发起一轮助手流式回复（新提问或基于已有用户消息重新生成）。 */
  const runAgentTurn = useCallback(
    async (
      userMessage: string,
      options?: {
        regenerateFromAssistantId?: string
        regenerateLastAssistant?: boolean
      },
    ) => {
      if (!workspaceId) {
        message.error(t('agents.noWorkspace'))
        return
      }
      const mid = prefs.selectedModelId
      if (!mid) {
        message.warning(t('agents.pickModel'))
        return
      }
      const apiBody = userMessage.trim()
      if (!apiBody) return

      const isRegenerate = Boolean(
        options?.regenerateFromAssistantId || options?.regenerateLastAssistant,
      )
      if (isRegenerate && !sessionId) {
        message.warning(t('agents.regenerateNoSession'))
        return
      }

      const asstId = `a-${Date.now()}`
      const asstMsg: AgentChatMsg = {
        id: asstId,
        role: 'assistant',
        content: '',
        reasoningSegments: [],
      }
      const regenId = options?.regenerateFromAssistantId

      let truncateOk = false
      if (isRegenerate) {
        setMessages((prev) => {
          let truncateIdx = regenId ? prev.findIndex((m) => m.id === regenId) : -1
          if (truncateIdx < 0 && options?.regenerateLastAssistant) {
            for (let i = prev.length - 1; i >= 0; i--) {
              if (prev[i]?.role === 'assistant') {
                truncateIdx = i
                break
              }
            }
          }
          if (truncateIdx < 0) return prev
          truncateOk = true
          return [...prev.slice(0, truncateIdx), asstMsg]
        })
        if (!truncateOk) {
          message.warning(t('agents.regenerateNoUserMessage'))
          return
        }
      } else {
        const userMsg: AgentChatMsg = { id: `u-${Date.now()}`, role: 'user', content: apiBody }
        setMessages((m) => [...m, userMsg, asstMsg])
      }

      userScrolledUpRef.current = false
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

      const setAsstTotalTokens = (total: number) => {
        setMessages((prev) =>
          prev.map((row) =>
            row.id === asstId && row.role === 'assistant'
              ? { ...row, totalTokens: total }
              : row,
          ),
        )
      }

      let sid = sessionId
      try {
        const modelRow = usableModels.find((m) => m.id === mid)
        const maxTok =
          modelRow?.max_tokens != null && Number.isFinite(modelRow.max_tokens)
            ? modelRow.max_tokens
            : null

        if (!sid) {
          if (isRegenerate) {
            message.warning(t('agents.regenerateNoSession'))
            return
          }
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

        const regenerateFromMessageId =
          isRegenerate && regenId && isAgentMessageUuid(regenId) ? regenId : null
        const regenerateLastAssistant = Boolean(
          isRegenerate &&
            (options?.regenerateLastAssistant || !regenerateFromMessageId),
        )

        const { runId } = await streamAgentRun(
          workspaceId,
          sid,
          {
            user_message: apiBody,
            model_id: mid,
            temperature: null,
            max_tokens: maxTok,
            preferred_skills: [],
            regenerate_from_message_id: regenerateFromMessageId,
            regenerate_last_assistant: regenerateLastAssistant,
            enable_thinking: thinkingEnabled,
          },
          (evt: AgentStreamEvent) => {
            if (evt.kind === 'done') return
            if (evt.kind === 'error') {
              pushAsstLog(`[error] ${evt.code}: ${evt.message}`)
              message.error(evt.message || evt.code)
              return
            }
            const ev = evt.event
            const traceLine = formatAgentV2TraceLine(ev, i18n.language)
            if (traceLine) pushAsstLog(traceLine)
            if (ev.type === 'llm.reasoning.segment_done') {
              const phase = String(ev.payload.phase ?? '')
              const stepId =
                ev.payload.step_id != null ? String(ev.payload.step_id) : null
              const skillId =
                ev.payload.skill_id != null ? String(ev.payload.skill_id) : null
              const tokens = Number(ev.payload.reasoning_tokens ?? 0)
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === asstId
                    ? {
                        ...m,
                        reasoningSegments: updateReasoningSegmentTokens(
                          m.reasoningSegments ?? [],
                          phase,
                          Number.isFinite(tokens) ? tokens : 0,
                          stepId,
                          skillId,
                        ),
                      }
                    : m,
                ),
              )
              return
            }
            if (ev.type === 'llm.reasoning.done') {
              const tokens = Number(ev.payload.reasoning_tokens ?? 0)
              if (Number.isFinite(tokens) && tokens > 0) {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === asstId
                      ? { ...m, reasoningTokens: Math.trunc(tokens) }
                      : m,
                  ),
                )
              }
              setReasoningOpenKeys([])
              return
            }
            if (ev.type === 'llm.delta') {
              const channel = String(ev.payload.channel ?? 'assistant')
              const text = String(ev.payload.text ?? '')
              if (!text) return
              if (channel === 'reasoning') {
                const phase = String(ev.payload.phase ?? 'subagent')
                const stepId =
                  ev.payload.step_id != null ? String(ev.payload.step_id) : null
                const skillId =
                  ev.payload.skill_id != null ? String(ev.payload.skill_id) : null
                setReasoningOpenKeys(['reasoning'])
                setMessages((prev) =>
                  prev.map((m) => {
                    if (m.id !== asstId) return m
                    const segments = appendReasoningDelta(
                      m.reasoningSegments ?? [],
                      phase,
                      text,
                      stepId,
                      skillId,
                    )
                    return { ...m, reasoningSegments: segments }
                  }),
                )
              } else {
                setTraceOpenKeys([])
                setReasoningOpenKeys([])
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === asstId ? { ...m, content: m.content + text } : m,
                  ),
                )
              }
              return
            }
            if (ev.type === 'llm.usage' || ev.type === 'run.finished') {
              if (ev.type === 'run.finished') {
                setReasoningOpenKeys([])
              }
              const raw =
                ev.type === 'llm.usage'
                  ? (ev.payload.total_usage ?? ev.payload.usage)
                  : ev.payload.usage
              const total = extractTotalTokens(raw)
              if (total != null) {
                setAsstTotalTokens(total)
              }
              const reasoningTotal = extractReasoningTokens(raw)
              if (reasoningTotal != null) {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === asstId ? { ...m, reasoningTokens: reasoningTotal } : m,
                  ),
                )
              }
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
          message.error(e.message)
          pushAsstLog(`[api] ${e.code}: ${e.message}`)
        } else {
          message.error(String(e))
          pushAsstLog(`[error] ${String(e)}`)
        }
      } finally {
        setStreaming(false)
        setReasoningOpenKeys([])
        abortRef.current = null
        if (sid && workspaceId) {
          const syncSid = sid
          const syncSessionFromServer = async () => {
            const detail = await getAgentSessionDetail(workspaceId, syncSid)
            const serverChat = agentMessagesToChat(detail.messages)
            setMessages((prev) => mergeAgentChatWithLocal(serverChat, prev))
          }
          try {
            await syncSessionFromServer()
            // memory.persist 在后台异步 patch usage，延迟再拉一次以展示完整 token。
            window.setTimeout(() => {
              void syncSessionFromServer().catch(() => {
                /* 二次同步失败不阻断 UI */
              })
            }, 2500)
          } catch {
            /* 同步失败不阻断 UI */
          }
        }
        void queryClient.invalidateQueries({ queryKey: ['agent-sessions', workspaceId] })
      }
    },
    [workspaceId, sessionId, prefs.selectedModelId, usableModels, queryClient, t, i18n.language, thinkingEnabled],
  )

  const onSend = useCallback(async () => {
    const apiBody = draft.trim()
    if (!apiBody) return
    setDraft('')
    await runAgentTurn(apiBody)
  }, [draft, runAgentTurn])

  /** 删除当前助手回复及其后消息，调用 runs 接口用同一条用户提问重新流式生成。 */
  const onRegenerate = useCallback(
    async (assistantMsgId: string) => {
      if (streaming) {
        message.warning(t('agents.regenerateWhileStreaming'))
        return
      }
      if (!sessionId) {
        message.warning(t('agents.regenerateNoSession'))
        return
      }
      const idx = messages.findIndex((m) => m.id === assistantMsgId)
      if (idx < 0) return
      let userMessage = ''
      for (let i = idx - 1; i >= 0; i--) {
        const row = messages[i]
        if (row?.role === 'user' && row.content.trim()) {
          userMessage = row.content.trim()
          break
        }
      }
      if (!userMessage) {
        message.warning(t('agents.regenerateNoUserMessage'))
        return
      }
      const isLastAssistant = messages[messages.length - 1]?.id === assistantMsgId
      const hasServerId = isAgentMessageUuid(assistantMsgId)
      if (!hasServerId && !isLastAssistant) {
        message.warning(t('agents.regenerateStaleMessage'))
        return
      }
      await runAgentTurn(userMessage, {
        regenerateFromAssistantId: assistantMsgId,
        regenerateLastAssistant: !hasServerId && isLastAssistant,
      })
    },
    [streaming, messages, sessionId, runAgentTurn, t],
  )

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

  const assistantProcessTrace = useCallback(
    (m: AgentChatMsg) => {
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
          expandIconPlacement="start"
          style={{ marginTop: 6, marginBottom: 4 }}
          items={[
            {
              key: 'trace',
              label: <span style={{ fontSize: 12 }}>{t('agents.assistantTrace')}</span>,
              children: (
                <div className="agents-page__process">
                  {logs.length === 0 ? (
                    <span
                      className="agents-page__process-wait"
                      role="status"
                      aria-label={t('agents.processLoading')}
                    >
                      <span className="agents-page__process-wait-dot" aria-hidden="true" />
                      <span className="agents-page__process-wait-dot" aria-hidden="true" />
                      <span className="agents-page__process-wait-dot" aria-hidden="true" />
                    </span>
                  ) : (
                    <div className="agents-page__process-log">
                      {logs.map((line, i) => (
                        <div key={`${m.id}-${i}-${line.slice(0, 48)}`}>{line}</div>
                      ))}
                    </div>
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

  const assistantReasoningTrace = useCallback(
    (m: AgentChatMsg) => {
      if (m.role !== 'assistant') return null
      if (!hasVisibleReasoning(m)) return null
      const isLatestAssistantCard = m.id === lastMessageId
      const segments = m.reasoningSegments ?? []
      const reasoningTokenCount = resolveReasoningTokenCount(m)
      const label =
        reasoningTokenCount > 0
          ? t('agents.reasoningTrace', {
              count: formatTokenNumber(reasoningTokenCount, i18n.language),
            })
          : t('agents.reasoningTracePlain')
      return (
        <Collapse
          className="agents-page__trace agents-page__reasoning-trace"
          size="small"
          ghost
          bordered={false}
          expandIconPlacement="start"
          style={{ marginTop: 4, marginBottom: 4 }}
          items={[
            {
              key: 'reasoning',
              label: (
                <span style={{ fontSize: 12 }}>{label}</span>
              ),
              children: (
                <div className="agents-page__process">
                  {segments.length > 0 ? (
                    segments.map((seg) => (
                      <div
                        key={`${m.id}-${seg.phase}-${seg.step_id ?? ''}-${seg.skill_id ?? ''}`}
                        className="agents-page__reasoning-segment"
                      >
                        <div className="agents-page__reasoning-segment-label">
                          {formatReasoningSegmentLabel(seg)}
                        </div>
                        {(seg.text ?? '').trim() ? (
                          <div className="agents-page__process-reasoning">{seg.text}</div>
                        ) : null}
                      </div>
                    ))
                  ) : (m.reasoning ?? '').trim() ? (
                    <div className="agents-page__process-reasoning">{m.reasoning}</div>
                  ) : null}
                </div>
              ),
            },
          ]}
          {...(isLatestAssistantCard
            ? {
                activeKey: reasoningOpenKeys,
                onChange: (k: string | string[]) =>
                  setReasoningOpenKeys(Array.isArray(k) ? k : k ? [k] : []),
              }
            : { defaultActiveKey: [] as string[] })}
        />
      )
    },
    [lastMessageId, reasoningOpenKeys, i18n.language, t],
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
                const sessionTokens = extractTotalTokens(s.usage)
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
                      <span className="agents-page__session-item-meta">
                        <span className="agents-page__session-item-time">
                          {loading ? (
                            <Spin size="small" />
                          ) : (
                            formatSessionTime(s.updated_at ?? s.created_at)
                          )}
                        </span>
                        {sessionTokens != null ? (
                          <span
                            className="agents-page__session-item-tokens"
                            title={formatTokenNumber(sessionTokens, i18n.language)}
                          >
                            {formatTokenCount(sessionTokens)}
                          </span>
                        ) : null}
                      </span>
                    </button>
                    <Dropdown menu={buildSessionRowMenu(s.id)} trigger={['click']}>
                      <Popconfirm
                        open={sessionDeleteConfirmId === s.id}
                        title={t('agents.deleteSessionConfirm')}
                        okText={t('agents.deleteSession')}
                        cancelText={t('common.cancel')}
                        okButtonProps={{ danger: true }}
                        onConfirm={(e) => {
                          e?.stopPropagation()
                          void handleDeleteSession(s.id)
                        }}
                        onCancel={(e) => {
                          e?.stopPropagation()
                          setSessionDeleteConfirmId(null)
                        }}
                        onOpenChange={(open) => {
                          if (!open) setSessionDeleteConfirmId(null)
                        }}
                      >
                        <Button
                          type="text"
                          size="small"
                          className="agents-page__session-item-menu"
                          icon={<MoreOutlined />}
                          aria-label={t('agents.sessionMenu')}
                          disabled={streaming}
                          onClick={(e) => e.stopPropagation()}
                        />
                      </Popconfirm>
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
          ref={chatScrollRef}
          className={`agents-page__scroll minerva-scrollbar-thin${showHero ? ' agents-page__scroll--hero' : ''}`}
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
                  {assistantProcessTrace(m)}
                  {assistantReasoningTrace(m)}
                  <Flex align="flex-start" gap={8}>
                    {streaming &&
                    m.role === 'assistant' &&
                    !m.content &&
                    !hasVisibleReasoning(m) ? (
                      <Spin size="small" style={{ marginTop: 4 }} />
                    ) : null}
                    {m.role === 'assistant' ? (
                      <div
                        className="agents-page__msg-body"
                        style={{ flex: 1, minWidth: 0, textAlign: 'left' }}
                      >
                        <AgentAssistantMarkdown markdown={m.content} />
                      </div>
                    ) : (
                      <div
                        className="agents-page__md-user-wrap agents-page__msg-body"
                        style={{ flex: 1, minWidth: 0 }}
                      >
                        <AgentAssistantMarkdown markdown={m.content} />
                      </div>
                    )}
                  </Flex>
                  {(m.content ?? '').trim().length > 0 ? (
                    <div
                      className="agents-page__msg-actions"
                      style={{
                        display: 'flex',
                        justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start',
                        gap: 2,
                      }}
                    >
                      {m.role === 'assistant' ? (
                        <Button
                          type="text"
                          size="small"
                          className="agents-page__msg-action-btn"
                          icon={<RedoOutlined />}
                          aria-label={t('agents.regenerateMessage')}
                          title={t('agents.regenerateMessage')}
                          disabled={streaming}
                          onClick={() => void onRegenerate(m.id)}
                        />
                      ) : null}
                      <Button
                        type="text"
                        size="small"
                        className="agents-page__msg-action-btn"
                        icon={<CopyOutlined />}
                        aria-label={t('agents.copyMessage')}
                        title={t('agents.copyMessage')}
                        onClick={() => void copyMessageBody(m.content)}
                      />
                      {m.role === 'assistant' &&
                      m.totalTokens != null &&
                      !(
                        streaming &&
                        m.id === lastMessageId &&
                        messages[messages.length - 1]?.role === 'assistant'
                      ) ? (
                        <Text
                          type="secondary"
                          className="agents-page__msg-token-usage"
                          aria-label={t('agents.tokenUsageAria', {
                            count: formatTokenNumber(m.totalTokens, i18n.language),
                          })}
                        >
                          {t('agents.tokenUsage', {
                            label: formatTokenNumber(m.totalTokens, i18n.language),
                          })}
                        </Text>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              </div>
            ))
          )}
          {messages.length > 0 ? (
            <div ref={listEndRef} className="agents-page__scroll-anchor" aria-hidden />
          ) : null}
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
                <button
                  type="button"
                  className={
                    thinkingEnabled
                      ? 'agents-page__thinking-mode-toggle agents-page__thinking-mode-toggle--active'
                      : 'agents-page__thinking-mode-toggle'
                  }
                  aria-pressed={thinkingEnabled}
                  disabled={streaming || usableModels.length === 0}
                  onClick={() => setThinkingEnabled((on) => !on)}
                >
                  {t('agents.thinkingMode')}
                </button>
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
