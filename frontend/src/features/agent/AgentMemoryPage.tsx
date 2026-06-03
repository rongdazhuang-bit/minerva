/**
 * mem0 memory management: persistent profiles and session memory list.
 */
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tabs,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  createAgentMemoryProfile,
  deleteAgentMem0Memory,
  deleteAgentMemoryProfile,
  getAgentV2Config,
  listAgentMem0Memories,
  listAgentMemoryProfiles,
  listAgentSessions,
  patchAgentMemoryProfile,
  type AgentMem0MemoryItemOut,
  type AgentMemoryProfileOut,
  type AgentSessionListItem,
} from '@/api/agent'
import { useAuth } from '@/app/AuthContext'
import { showAppError, useAppMessage } from '@/app/useAppMessage'
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'
import './AgentMemoryPage.css'

const { Text } = Typography
const { TextArea } = Input

type ProfileScope = 'workspace' | 'session'

/** Memory profiles and mem0 rows when backend is mem0. */
export function AgentMemoryPage() {
  const { t } = useTranslation()
  const messageApi = useAppMessage()
  const { workspaceId } = useAuth()
  const [backend, setBackend] = useState<string | null>(null)
  const [profiles, setProfiles] = useState<AgentMemoryProfileOut[]>([])
  const [profilesLoading, setProfilesLoading] = useState(false)
  const [sessions, setSessions] = useState<AgentSessionListItem[]>([])
  const [memorySessionId, setMemorySessionId] = useState<string | null>(null)
  const [memories, setMemories] = useState<AgentMem0MemoryItemOut[]>([])
  const [memoriesLoading, setMemoriesLoading] = useState(false)
  const [profileModalOpen, setProfileModalOpen] = useState(false)
  const [editingProfile, setEditingProfile] = useState<AgentMemoryProfileOut | null>(null)
  const [profileForm] = Form.useForm<{
    scope: ProfileScope
    session_id?: string
    profile_text: string
  }>()

  useEffect(() => {
    if (!workspaceId) return
    void getAgentV2Config(workspaceId)
      .then((c) => setBackend(c.memory_backend))
      .catch(() => setBackend('sql'))
  }, [workspaceId])

  const loadProfiles = useCallback(async () => {
    if (!workspaceId || backend !== 'mem0') return
    setProfilesLoading(true)
    try {
      setProfiles(await listAgentMemoryProfiles(workspaceId))
    } catch (e) {
      showAppError(messageApi, t, e)
    } finally {
      setProfilesLoading(false)
    }
  }, [workspaceId, backend, messageApi, t])

  const loadSessions = useCallback(async () => {
    if (!workspaceId) return
    try {
      const data = await listAgentSessions(workspaceId, { limit: 100 })
      setSessions(data.sessions)
      if (!memorySessionId && data.sessions[0]) {
        setMemorySessionId(data.sessions[0].id)
      }
    } catch (e) {
      showAppError(messageApi, t, e)
    }
  }, [workspaceId, memorySessionId, messageApi, t])

  const loadMemories = useCallback(async () => {
    if (!workspaceId || !memorySessionId || backend !== 'mem0') return
    setMemoriesLoading(true)
    try {
      const data = await listAgentMem0Memories(workspaceId, memorySessionId)
      setMemories(data.items)
    } catch (e) {
      showAppError(messageApi, t, e)
    } finally {
      setMemoriesLoading(false)
    }
  }, [workspaceId, memorySessionId, backend, messageApi, t])

  useEffect(() => {
    void loadProfiles()
    void loadSessions()
  }, [loadProfiles, loadSessions])

  useEffect(() => {
    void loadMemories()
  }, [loadMemories])

  const openCreateProfile = () => {
    setEditingProfile(null)
    profileForm.setFieldsValue({
      scope: 'workspace',
      profile_text: '',
    })
    setProfileModalOpen(true)
  }

  const openEditProfile = (row: AgentMemoryProfileOut) => {
    setEditingProfile(row)
    profileForm.setFieldsValue({
      scope: row.session_id ? 'session' : 'workspace',
      session_id: row.session_id ?? undefined,
      profile_text: row.profile_text,
    })
    setProfileModalOpen(true)
  }

  const saveProfile = async () => {
    if (!workspaceId) return
    const values = await profileForm.validateFields()
    try {
      if (editingProfile) {
        await patchAgentMemoryProfile(workspaceId, editingProfile.id, {
          profile_text: values.profile_text,
        })
      } else {
        await createAgentMemoryProfile(workspaceId, {
          session_id: values.scope === 'session' ? values.session_id ?? null : null,
          profile_text: values.profile_text,
        })
      }
      void messageApi.success(
        t('agents.memory.saveSuccess', { defaultValue: '已保存' }),
      )
      setProfileModalOpen(false)
      await loadProfiles()
    } catch (e) {
      showAppError(messageApi, t, e)
    }
  }

  const handleDeleteProfile = async (id: string) => {
    if (!workspaceId) return
    try {
      await deleteAgentMemoryProfile(workspaceId, id)
      void messageApi.success(
        t('agents.memory.deleteProfileSuccess', { defaultValue: '画像已删除' }),
      )
      await loadProfiles()
    } catch (e) {
      showAppError(messageApi, t, e)
    }
  }

  const handleDeleteMemory = async (memoryId: string) => {
    if (!workspaceId) return
    try {
      await deleteAgentMem0Memory(workspaceId, memoryId)
      void messageApi.success(
        t('agents.memory.deleteMemorySuccess', { defaultValue: '记忆已删除' }),
      )
      await loadMemories()
    } catch (e) {
      showAppError(messageApi, t, e)
    }
  }

  const profileColumns: ColumnsType<AgentMemoryProfileOut> = useMemo(
    () => [
      {
        title: t('agents.memory.colScope', { defaultValue: '范围' }),
        key: 'scope',
        width: 120,
        render: (_, row) =>
          row.session_id
            ? t('agents.memory.scopeSession', { defaultValue: '会话' })
            : t('agents.memory.scopeWorkspace', { defaultValue: '工作区' }),
      },
      {
        title: t('agents.memory.colSession', { defaultValue: '会话 ID' }),
        dataIndex: 'session_id',
        key: 'session_id',
        ellipsis: true,
        render: (v: string | null) => v ?? '—',
      },
      {
        title: t('agents.memory.colText', { defaultValue: '画像内容' }),
        dataIndex: 'profile_text',
        key: 'profile_text',
        ellipsis: true,
      },
      {
        title: t('agents.memory.colActions', { defaultValue: '操作' }),
        key: 'actions',
        width: 120,
        render: (_, row) => (
          <Space size={4}>
            <Button type="link" size="small" onClick={() => openEditProfile(row)}>
              {t('agents.memory.edit', { defaultValue: '编辑' })}
            </Button>
            <Popconfirm
              title={t('agents.memory.deleteProfileConfirm', {
                defaultValue: '确定删除该画像？',
              })}
              onConfirm={() => void handleDeleteProfile(row.id)}
            >
              <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                {t('agents.memory.delete', { defaultValue: '删除' })}
              </Button>
            </Popconfirm>
          </Space>
        ),
      },
    ],
    [t],
  )

  const memoryColumns: ColumnsType<AgentMem0MemoryItemOut> = useMemo(
    () => [
      {
        title: t('agents.memory.colMemory', { defaultValue: '记忆' }),
        dataIndex: 'memory',
        key: 'memory',
        ellipsis: true,
      },
      {
        title: t('agents.memory.colActions', { defaultValue: '操作' }),
        key: 'actions',
        width: 100,
        render: (_, row) => (
          <Popconfirm
            title={t('agents.memory.deleteMemoryConfirm', {
              defaultValue: '确定删除该条记忆？',
            })}
            onConfirm={() => void handleDeleteMemory(row.id)}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              {t('agents.memory.delete', { defaultValue: '删除' })}
            </Button>
          </Popconfirm>
        ),
      },
    ],
    [t],
  )

  if (backend === null) {
    return (
      <div className="minerva-agent-memory-page">
        <Card loading variant="borderless" />
      </div>
    )
  }

  if (backend !== 'mem0') {
    return (
      <div className="minerva-agent-memory-page">
        <Alert
          type="info"
          showIcon
          message={t('agents.memory.disabled', {
            defaultValue:
              '当前环境未启用 mem0 记忆后端（AGENT_MEMORY_BACKEND=sql）。请在环境变量中切换为 mem0 后使用本页。',
          })}
        />
      </div>
    )
  }

  return (
    <div className="minerva-agent-memory-page">
      <Card className="minerva-agent-memory-page__card" variant="borderless">
        <Text strong className="minerva-agent-memory-page__title">
          {t('agents.memory.title', { defaultValue: '记忆管理' })}
        </Text>
        <Tabs
          items={[
            {
              key: 'profiles',
              label: t('agents.memory.tabProfiles', { defaultValue: '持久画像' }),
              children: (
                <>
                  <div className="minerva-agent-memory-page__toolbar">
                    <Button type="primary" icon={<PlusOutlined />} onClick={openCreateProfile}>
                      {t('agents.memory.newProfile', { defaultValue: '新建画像' })}
                    </Button>
                  </div>
                  <div className="minerva-agent-memory-page__table-wrap minerva-scrollbar-styled">
                    <Table<AgentMemoryProfileOut>
                      rowKey="id"
                      loading={profilesLoading}
                      columns={profileColumns}
                      dataSource={profiles}
                      pagination={{ pageSize: DEFAULT_PAGE_SIZE, showSizeChanger: false }}
                      scroll={{ x: 'max-content' }}
                    />
                  </div>
                </>
              ),
            },
            {
              key: 'memories',
              label: t('agents.memory.tabMemories', { defaultValue: 'mem0 记忆' }),
              children: (
                <>
                  <Space className="minerva-agent-memory-page__toolbar" wrap>
                    <Text>{t('agents.memory.pickSession', { defaultValue: '会话' })}</Text>
                    <Select
                      style={{ minWidth: 280 }}
                      value={memorySessionId ?? undefined}
                      options={sessions.map((s) => ({
                        value: s.id,
                        label: s.title || s.preview || s.id,
                      }))}
                      onChange={(v) => setMemorySessionId(v)}
                      allowClear
                      placeholder={t('agents.memory.pickSessionPlaceholder', {
                        defaultValue: '选择会话',
                      })}
                    />
                    <Button onClick={() => void loadMemories()}>
                      {t('agents.memory.refresh', { defaultValue: '刷新' })}
                    </Button>
                  </Space>
                  <div className="minerva-agent-memory-page__table-wrap minerva-scrollbar-styled">
                    <Table<AgentMem0MemoryItemOut>
                      rowKey="id"
                      loading={memoriesLoading}
                      columns={memoryColumns}
                      dataSource={memories}
                      pagination={{ pageSize: DEFAULT_PAGE_SIZE, showSizeChanger: false }}
                      scroll={{ x: 'max-content' }}
                    />
                  </div>
                </>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title={
          editingProfile
            ? t('agents.memory.editProfile', { defaultValue: '编辑画像' })
            : t('agents.memory.newProfile', { defaultValue: '新建画像' })
        }
        open={profileModalOpen}
        onCancel={() => setProfileModalOpen(false)}
        onOk={() => void saveProfile()}
        destroyOnClose
        width={640}
      >
        <Form form={profileForm} layout="vertical">
          {!editingProfile ? (
            <>
              <Form.Item name="scope" label={t('agents.memory.scope', { defaultValue: '范围' })}>
                <Select
                  options={[
                    {
                      value: 'workspace',
                      label: t('agents.memory.scopeWorkspace', { defaultValue: '工作区' }),
                    },
                    {
                      value: 'session',
                      label: t('agents.memory.scopeSession', { defaultValue: '会话' }),
                    },
                  ]}
                />
              </Form.Item>
              <Form.Item noStyle shouldUpdate>
                {() =>
                  profileForm.getFieldValue('scope') === 'session' ? (
                    <Form.Item
                      name="session_id"
                      label={t('agents.memory.colSession', { defaultValue: '会话' })}
                      rules={[{ required: true }]}
                    >
                      <Select
                        options={sessions.map((s) => ({
                          value: s.id,
                          label: s.title || s.preview || s.id,
                        }))}
                      />
                    </Form.Item>
                  ) : null
                }
              </Form.Item>
            </>
          ) : null}
          <Form.Item
            name="profile_text"
            label={t('agents.memory.colText', { defaultValue: '画像内容' })}
            rules={[{ required: true }]}
          >
            <TextArea rows={8} maxLength={8000} showCount allowClear />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
