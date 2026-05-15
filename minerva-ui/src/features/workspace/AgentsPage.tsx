/**
 * 工作区「智能体」对话页：Kimi 式布局；模型仅从已配置的模型提供商中选择，发送前拉取详情以连接上游。
 */
import { PlusOutlined, RobotOutlined, SendOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Collapse,
  Divider,
  Flex,
  Input,
  Select,
  Spin,
  Typography,
  message as antdMessage,
} from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { createAgentSession, streamAgentRun, type AgentSseEvent } from '@/api/agent'
import { ApiError } from '@/api/client'
import { getModelProvider, listModelProviders, type ModelProviderListItem } from '@/api/modelProviders'
import { useAuth } from '@/app/AuthContext'
import './AgentsPage.css'

const { Text, Paragraph, Title } = Typography

const UI_PREFS_KEY = 'minerva-agent-ui-v2'

type UiPrefs = {
  selectedModelId: string | null
  skillIdsCsv: string
}

function loadPrefs(): UiPrefs {
  try {
    const raw = sessionStorage.getItem(UI_PREFS_KEY)
    if (!raw) throw new Error('empty')
    const j = JSON.parse(raw) as Partial<UiPrefs>
    return {
      selectedModelId: typeof j.selectedModelId === 'string' ? j.selectedModelId : null,
      skillIdsCsv: typeof j.skillIdsCsv === 'string' ? j.skillIdsCsv : 'example_echo',
    }
  } catch {
    return { selectedModelId: null, skillIdsCsv: 'example_echo' }
  }
}

function savePrefs(p: UiPrefs) {
  sessionStorage.setItem(UI_PREFS_KEY, JSON.stringify(p))
}

function parseSkillIds(csv: string): string[] {
  return csv
    .split(/[,，\s]+/)
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean)
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
}

/** 工作区智能体对话主界面（类 Kimi：侧栏 + 主区 + 底部合成器，右侧选模型）。 */
export function AgentsPage() {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const [prefs, setPrefs] = useState<UiPrefs>(() => loadPrefs())
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [processLines, setProcessLines] = useState<string[]>([])
  const [draft, setDraft] = useState('')
  const [streaming, setStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const listEndRef = useRef<HTMLDivElement | null>(null)

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

  const setSkillIdsCsv = useCallback((csv: string) => {
    setPrefs((p) => {
      const next = { ...p, skillIdsCsv: csv }
      savePrefs(next)
      return next
    })
  }, [])

  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, processLines, streaming])

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
    setProcessLines([])
    setStreaming(false)
    antdMessage.info(t('agents.newChatHint'))
  }, [t])

  const appendProcess = useCallback((line: string) => {
    setProcessLines((prev) => [...prev.slice(-200), line])
  }, [])

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
    setProcessLines([])

    const ac = new AbortController()
    abortRef.current = ac

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
        appendProcess(`[session] ${sid}`)
      }

      const skillIds = parseSkillIds(prefs.skillIdsCsv)
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
          skill_ids: skillIds,
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
            appendProcess(`[run_started] ${evt.run_id}`)
            return
          }
          if (typ === 'assistant_delta' && typeof evt.text === 'string') {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === asstId ? { ...m, content: m.content + evt.text } : m,
              ),
            )
            return
          }
          if (typ === 'log' || typ === 'step') {
            const body = typeof evt.message === 'string' ? evt.message : JSON.stringify(evt)
            appendProcess(`[${typ}] ${body}`)
            return
          }
          if (typ === 'tool_start' || typ === 'tool_result') {
            appendProcess(`[${typ}] ${JSON.stringify(evt)}`)
            return
          }
          if (typ === 'error') {
            const code = typeof evt.code === 'string' ? evt.code : 'error'
            const msg = typeof evt.message === 'string' ? evt.message : ''
            appendProcess(`[error] ${code}: ${msg}`)
            antdMessage.error(msg || code)
            return
          }
          if (typ === 'run_finished') {
            appendProcess(`[run_finished] ${String(evt.status ?? '')}`)
          }
        },
        ac.signal,
      )
      antdMessage.success(t('agents.runComplete'))
    } catch (e) {
      if ((e as Error).name === 'AbortError') {
        appendProcess('[aborted]')
      } else if (e instanceof ApiError) {
        antdMessage.error(e.message)
        appendProcess(`[api] ${e.code}: ${e.message}`)
      } else {
        antdMessage.error(String(e))
        appendProcess(`[error] ${String(e)}`)
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
    prefs.skillIdsCsv,
    appendProcess,
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

  return (
    <div className="agents-page">
      <aside className="agents-page__sider">
        <Button type="primary" block onClick={handleNewChat}>
          {t('agents.newChat')}
        </Button>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {t('agents.sidebarHint')}
        </Text>
        <Divider style={{ margin: '8px 0' }} />
        <Collapse
          size="small"
          ghost
          items={[
            {
              key: 'proc',
              label: (
                <span style={{ fontSize: 12 }}>
                  <PlusOutlined style={{ marginRight: 6 }} />
                  {t('agents.processPanel')}
                </span>
              ),
              children: (
                <div className="agents-page__process">
                  {processLines.length === 0 ? (
                    <Text type="secondary">{t('agents.processEmpty')}</Text>
                  ) : (
                    processLines.map((line, i) => (
                      <div key={`${i}-${line.slice(0, 48)}`}>{line}</div>
                    ))
                  )}
                </div>
              ),
            },
          ]}
        />
      </aside>

      <div className="agents-page__main">
        <div className="agents-page__scroll">
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
                <Card
                  size="small"
                  style={{
                    maxWidth: '85%',
                    background:
                      m.role === 'user'
                        ? 'var(--minerva-primary-dim, rgba(56,189,248,0.12))'
                        : 'var(--minerva-surface, #1b2838)',
                    borderColor: 'var(--minerva-border, #2d3f55)',
                  }}
                >
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {m.role === 'user' ? t('agents.roleUser') : t('agents.roleAssistant')}
                  </Text>
                  <Flex align="flex-start" gap={8}>
                    {streaming && m.role === 'assistant' && !m.content ? (
                      <Spin size="small" style={{ marginTop: 4 }} />
                    ) : null}
                    <Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap', flex: 1 }}>
                      {m.content || '\u00a0'}
                    </Paragraph>
                  </Flex>
                </Card>
              </div>
            ))
          )}
          <div ref={listEndRef} />
        </div>

        <div className="agents-page__composer-wrap">
          <div className="agents-page__composer">
            <Input.TextArea
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
              <Flex align="center" gap={8} style={{ flex: 1, minWidth: 0 }}>
                <Text type="secondary" style={{ flexShrink: 0, fontSize: 12 }}>
                  {t('agents.skillIdsShort')}
                </Text>
                <Input
                  allowClear
                  size="small"
                  style={{ maxWidth: 220 }}
                  value={prefs.skillIdsCsv}
                  onChange={(e) => setSkillIdsCsv(e.target.value)}
                  placeholder="example_echo"
                  disabled={streaming}
                />
              </Flex>
              <Flex align="center" gap={10}>
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
