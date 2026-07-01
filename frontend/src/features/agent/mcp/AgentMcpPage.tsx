import { DeleteOutlined, EditOutlined, PlusOutlined, ToolOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Drawer,
  Form,
  Input,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { listAgentSkills } from '@/api/agent'
import {
  createMcpClient,
  createMcpServer,
  deleteMcpClient,
  deleteMcpServer,
  getMcpClient,
  getMcpRuntimeStatus,
  listMcpClients,
  listMcpServers,
  patchMcpClient,
  patchMcpServer,
  testMcpClient,
  type McpClientListItem,
  type McpServerListItem,
  type McpTransport,
} from '@/api/mcp'
import { useAuth } from '@/app/AuthContext'
import { useAppMessage } from '@/app/useAppMessage'
import './AgentMcpPage.css'
import { McpToolExplorerModal } from './McpToolExplorerModal'

type ClientFormValues = {
  name: string
  transport: McpTransport
  enabled: boolean
  remark?: string
  command?: string
  args?: string
  cwd?: string
  url?: string
  envJson?: string
  headersJson?: string
}

type ServerFormValues = {
  name: string
  slug: string
  enabled: boolean
  auth_type: 'NONE' | 'BEARER' | 'API_KEY'
  auth_secret?: string
  remark?: string
  include_all_builtin?: boolean
  include_all_clients?: boolean
  builtin_skills?: string[]
  mcp_client_ids?: string[]
}

function configToClientForm(
  transport: McpTransport,
  config: Record<string, unknown>,
  secrets: Record<string, unknown>,
): Partial<ClientFormValues> {
  const values: Partial<ClientFormValues> = {}
  if (transport === 'STDIO') {
    values.command = typeof config.command === 'string' ? config.command : undefined
    values.args = Array.isArray(config.args) ? config.args.map(String).join('\n') : undefined
    values.cwd = typeof config.cwd === 'string' ? config.cwd : undefined
    if (secrets.env && typeof secrets.env === 'object' && !('_redacted' in secrets)) {
      values.envJson = JSON.stringify(secrets.env, null, 2)
    }
  } else {
    values.url = typeof config.url === 'string' ? config.url : undefined
    if (secrets.headers && typeof secrets.headers === 'object' && !('_redacted' in secrets)) {
      values.headersJson = JSON.stringify(secrets.headers, null, 2)
    }
  }
  return values
}

/** Workspace MCP client/server management (test-before-save for clients). */
export function AgentMcpPage() {
  const { t } = useTranslation()
  const messageApi = useAppMessage()
  const { workspaceId, isWorkspaceAdmin } = useAuth()
  const queryClient = useQueryClient()
  const [clientDrawerOpen, setClientDrawerOpen] = useState(false)
  const [serverDrawerOpen, setServerDrawerOpen] = useState(false)
  const [editingClient, setEditingClient] = useState<McpClientListItem | null>(null)
  const [editingServer, setEditingServer] = useState<McpServerListItem | null>(null)
  const [clientDetailLoading, setClientDetailLoading] = useState(false)
  const [clientForm] = Form.useForm<ClientFormValues>()
  const [serverForm] = Form.useForm<ServerFormValues>()
  const [explorerClient, setExplorerClient] = useState<McpClientListItem | null>(null)
  const transport = Form.useWatch('transport', clientForm) as McpTransport | undefined
  const includeAllBuiltin = Form.useWatch('include_all_builtin', serverForm) as boolean | undefined
  const includeAllClients = Form.useWatch('include_all_clients', serverForm) as boolean | undefined

  const { data: runtimeStatus } = useQuery({
    queryKey: ['mcp-runtime-status', workspaceId],
    queryFn: () => getMcpRuntimeStatus(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const { data: clients = [], isLoading: clientsLoading } = useQuery({
    queryKey: ['mcp-clients', workspaceId],
    queryFn: () => listMcpClients(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const { data: servers = [], isLoading: serversLoading } = useQuery({
    queryKey: ['mcp-servers', workspaceId],
    queryFn: () => listMcpServers(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const { data: agentSkillsData } = useQuery({
    queryKey: ['agent-skills', workspaceId],
    queryFn: () => listAgentSkills(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const skillOptions = useMemo(
    () =>
      (agentSkillsData?.skills ?? []).map((skill) => ({
        value: skill.id,
        label: `${skill.id} — ${skill.description}`,
      })),
    [agentSkillsData],
  )

  const clientOptions = useMemo(
    () =>
      clients.map((client) => ({
        value: client.id,
        label: client.name,
        disabled: !client.enabled,
      })),
    [clients],
  )

  const invalidate = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['mcp-clients', workspaceId] })
    void queryClient.invalidateQueries({ queryKey: ['mcp-servers', workspaceId] })
  }, [queryClient, workspaceId])

  const buildClientPayload = (values: ClientFormValues, options?: { omitSecrets?: boolean }) => {
    const transportVal = values.transport
    const config: Record<string, unknown> = {}
    const secrets: Record<string, unknown> = {}
    if (transportVal === 'STDIO') {
      config.command = values.command?.trim()
      config.args = (values.args || '')
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean)
      if (values.cwd?.trim()) config.cwd = values.cwd.trim()
      if (values.envJson?.trim()) {
        secrets.env = JSON.parse(values.envJson) as Record<string, string>
      }
    } else {
      config.url = values.url?.trim()
      if (values.headersJson?.trim()) {
        secrets.headers = JSON.parse(values.headersJson) as Record<string, string>
      }
    }
    const body = {
      name: values.name.trim(),
      transport: transportVal,
      config,
      secrets,
      enabled: values.enabled,
      remark: values.remark?.trim() || null,
    }
    if (options?.omitSecrets) {
      delete (body as { secrets?: Record<string, unknown> }).secrets
    }
    return body
  }

  const openEditClient = useCallback(
    async (row: McpClientListItem) => {
      if (!workspaceId) return
      setEditingClient(row)
      clientForm.resetFields()
      setClientDrawerOpen(true)
      setClientDetailLoading(true)
      try {
        const detail = await getMcpClient(workspaceId, row.id)
        clientForm.setFieldsValue({
          name: detail.name,
          transport: detail.transport,
          enabled: detail.enabled,
          remark: detail.remark ?? undefined,
          ...configToClientForm(detail.transport, detail.config ?? {}, detail.secrets ?? {}),
        })
      } catch (err) {
        messageApi.error(err instanceof Error ? err.message : t('common.loadFailed', { defaultValue: '加载失败' }))
        setClientDrawerOpen(false)
        setEditingClient(null)
      } finally {
        setClientDetailLoading(false)
      }
    },
    [clientForm, messageApi, t, workspaceId],
  )

  const saveClientMutation = useMutation({
    mutationFn: async (values: ClientFormValues) => {
      const secretsProvided =
        Boolean(values.envJson?.trim()) || Boolean(values.headersJson?.trim())
      const omitSecrets = Boolean(editingClient?.has_secrets && !secretsProvided)
      const body = buildClientPayload(values, { omitSecrets })
      if (editingClient) {
        return patchMcpClient(workspaceId!, editingClient.id, body)
      }
      const test = await testMcpClient(workspaceId!, {
        transport: body.transport,
        config: body.config,
        secrets: body.secrets ?? {},
      })
      if (!test.ok) {
        throw new Error(test.error_message || t('mcp.testFailed', { defaultValue: '连通性测试失败' }))
      }
      return createMcpClient(workspaceId!, body)
    },
    onSuccess: () => {
      messageApi.success(t('mcp.saveSuccess', { defaultValue: '已保存' }))
      setClientDrawerOpen(false)
      setEditingClient(null)
      invalidate()
    },
    onError: (err: Error) => {
      messageApi.error(err.message)
    },
  })

  const saveServerMutation = useMutation({
    mutationFn: async (values: ServerFormValues) => {
      const body = {
        name: values.name.trim(),
        slug: values.slug.trim().toLowerCase(),
        enabled: values.enabled,
        auth_type: values.auth_type,
        auth_secret: values.auth_secret?.trim() || null,
        remark: values.remark?.trim() || null,
        exposure: {
          include_all_builtin: Boolean(values.include_all_builtin),
          include_all_clients: Boolean(values.include_all_clients),
          builtin_skills: values.include_all_builtin ? [] : values.builtin_skills ?? [],
          mcp_client_ids: values.include_all_clients ? [] : values.mcp_client_ids ?? [],
        },
      }
      if (editingServer) {
        return patchMcpServer(workspaceId!, editingServer.id, body)
      }
      return createMcpServer(workspaceId!, body)
    },
    onSuccess: () => {
      messageApi.success(t('mcp.saveSuccess', { defaultValue: '已保存' }))
      setServerDrawerOpen(false)
      setEditingServer(null)
      invalidate()
    },
    onError: (err: Error) => {
      messageApi.error(err.message)
    },
  })

  const clientColumns: ColumnsType<McpClientListItem> = useMemo(
    () => [
      { title: t('mcp.colName', { defaultValue: '名称' }), dataIndex: 'name' },
      {
        title: t('mcp.colUrl', { defaultValue: 'URL' }),
        dataIndex: 'url',
        ellipsis: true,
        render: (url: string | null) => url ?? '—',
      },
      { title: t('mcp.colTransport', { defaultValue: '传输' }), dataIndex: 'transport' },
      {
        title: t('mcp.colEnabled', { defaultValue: '启用' }),
        dataIndex: 'enabled',
        render: (v: boolean) => (v ? <Tag color="green">ON</Tag> : <Tag>OFF</Tag>),
      },
      {
        title: t('mcp.colLastTest', { defaultValue: '最近测试' }),
        render: (_, row) =>
          row.last_test_ok == null ? '—' : row.last_test_ok ? 'OK' : 'FAIL',
      },
      {
        title: t('common.actions', { defaultValue: '操作' }),
        render: (_: unknown, row: McpClientListItem) => (
          <Space>
            <Button
              type="link"
              icon={<ToolOutlined />}
              aria-label={t('mcp.exploreTools', { defaultValue: '工具探索' })}
              onClick={() => setExplorerClient(row)}
            />
            {isWorkspaceAdmin ? (
              <>
                <Button type="link" icon={<EditOutlined />} onClick={() => void openEditClient(row)} />
                <Popconfirm
                  title={t('mcp.deleteClientConfirm', { defaultValue: '确定删除此 MCP 客户端？' })}
                  onConfirm={async () => {
                    await deleteMcpClient(workspaceId!, row.id)
                    invalidate()
                  }}
                >
                  <Button type="link" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              </>
            ) : null}
          </Space>
        ),
      },
    ],
    [invalidate, isWorkspaceAdmin, openEditClient, t, workspaceId],
  )

  const serverColumns: ColumnsType<McpServerListItem> = useMemo(
    () => [
      { title: t('mcp.colName', { defaultValue: '名称' }), dataIndex: 'name' },
      { title: 'slug', dataIndex: 'slug' },
      { title: t('mcp.colAuth', { defaultValue: '鉴权' }), dataIndex: 'auth_type' },
      ...(isWorkspaceAdmin
        ? [
            {
              title: t('common.actions', { defaultValue: '操作' }),
              render: (_: unknown, row: McpServerListItem) => (
                <Space>
                  <Button
                    type="link"
                    icon={<EditOutlined />}
                    onClick={() => {
                      setEditingServer(row)
                      const exposure = (row.exposure ?? {}) as Record<string, unknown>
                      serverForm.setFieldsValue({
                        name: row.name,
                        slug: row.slug,
                        enabled: row.enabled,
                        auth_type: row.auth_type as ServerFormValues['auth_type'],
                        remark: row.remark ?? undefined,
                        include_all_builtin: Boolean(exposure.include_all_builtin),
                        include_all_clients: Boolean(exposure.include_all_clients),
                        builtin_skills: Array.isArray(exposure.builtin_skills)
                          ? exposure.builtin_skills.map(String)
                          : [],
                        mcp_client_ids: Array.isArray(exposure.mcp_client_ids)
                          ? exposure.mcp_client_ids.map(String)
                          : [],
                      })
                      setServerDrawerOpen(true)
                    }}
                  />
                  <Popconfirm
                    title={t('mcp.deleteServerConfirm', { defaultValue: '确定删除此 MCP 服务端？' })}
                    onConfirm={async () => {
                      await deleteMcpServer(workspaceId!, row.id)
                      invalidate()
                    }}
                  >
                    <Button type="link" danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                </Space>
              ),
            } as ColumnsType<McpServerListItem>[number],
          ]
        : []),
    ],
    [invalidate, isWorkspaceAdmin, serverForm, t, workspaceId],
  )

  if (!workspaceId) {
    return <Alert type="warning" message={t('agents.noWorkspace')} />
  }

  return (
    <div className="minerva-agent-mcp-page">
      <Card className="minerva-agent-mcp-page__card" variant="borderless">
        {!isWorkspaceAdmin ? (
          <Alert
            type="info"
            showIcon
            className="minerva-agent-mcp-page__banner"
            message={t('mcp.readOnlyHint', { defaultValue: '仅工作区管理员可新增或修改 MCP 配置。' })}
          />
        ) : null}
        <Tabs
          className="minerva-agent-mcp-page__tabs"
          items={[
            {
              key: 'clients',
              label: t('mcp.clientsTab', { defaultValue: 'MCP 客户端' }),
              children: (
                <div className="minerva-agent-mcp-page__tab-pane">
                  {!runtimeStatus?.client_enabled && (
                    <Alert
                      type="info"
                      showIcon
                      className="minerva-agent-mcp-page__banner"
                      message={t('mcp.clientDisabledBanner', {
                        defaultValue: 'MCP 客户端未启用，配置仅存储，对话中不会加载。',
                      })}
                    />
                  )}
                  {isWorkspaceAdmin ? (
                    <div className="minerva-agent-mcp-page__toolbar">
                      <Button
                        type="primary"
                        icon={<PlusOutlined />}
                        onClick={() => {
                          setEditingClient(null)
                          clientForm.resetFields()
                          clientForm.setFieldsValue({
                            transport: 'SSE',
                            enabled: true,
                          })
                          setClientDrawerOpen(true)
                        }}
                      >
                        {t('mcp.addClient', { defaultValue: '新增客户端' })}
                      </Button>
                    </div>
                  ) : null}
                  <div className="minerva-agent-mcp-page__table-wrap minerva-scrollbar-styled">
                    <Table
                      rowKey="id"
                      loading={clientsLoading}
                      columns={clientColumns}
                      dataSource={clients}
                      pagination={{ pageSize: 10 }}
                      scroll={{ x: 'max-content' }}
                    />
                  </div>
                </div>
              ),
            },
            {
              key: 'servers',
              label: t('mcp.serversTab', { defaultValue: 'MCP 服务端' }),
              children: (
                <div className="minerva-agent-mcp-page__tab-pane">
                  {!runtimeStatus?.server_enabled && (
                    <Alert
                      type="info"
                      showIcon
                      className="minerva-agent-mcp-page__banner"
                      message={t('mcp.serverDisabledBanner', {
                        defaultValue: 'MCP 服务端未启用，配置仅存储，对外路由不会挂载。',
                      })}
                    />
                  )}
                  {isWorkspaceAdmin ? (
                    <div className="minerva-agent-mcp-page__toolbar">
                      <Button
                        type="primary"
                        icon={<PlusOutlined />}
                        onClick={() => {
                          setEditingServer(null)
                          serverForm.resetFields()
                          serverForm.setFieldsValue({
                            enabled: true,
                            auth_type: 'NONE',
                            builtin_skills: [],
                            mcp_client_ids: [],
                          })
                          setServerDrawerOpen(true)
                        }}
                      >
                        {t('mcp.addServer', { defaultValue: '新增服务端' })}
                      </Button>
                    </div>
                  ) : null}
                  <div className="minerva-agent-mcp-page__table-wrap minerva-scrollbar-styled">
                    <Table
                      rowKey="id"
                      loading={serversLoading}
                      columns={serverColumns}
                      dataSource={servers}
                      pagination={{ pageSize: 10 }}
                      scroll={{ x: 'max-content' }}
                    />
                  </div>
                </div>
              ),
            },
          ]}
        />
      </Card>

      <Drawer
        title={
          editingClient
            ? t('mcp.editClient', { defaultValue: '编辑 MCP 客户端' })
            : t('mcp.addClient', { defaultValue: '新增客户端' })
        }
        open={clientDrawerOpen}
        width={520}
        onClose={() => setClientDrawerOpen(false)}
        extra={
          isWorkspaceAdmin ? (
            <Button
              type="primary"
              loading={saveClientMutation.isPending || clientDetailLoading}
              disabled={clientDetailLoading}
              onClick={() => void clientForm.submit()}
            >
              {t('common.save', { defaultValue: '保存' })}
            </Button>
          ) : null
        }
      >
        <Form form={clientForm} layout="vertical" onFinish={(v) => saveClientMutation.mutate(v)}>
          <Form.Item name="name" label={t('mcp.colName', { defaultValue: '名称' })} rules={[{ required: true }]}>
            <Input allowClear disabled={!isWorkspaceAdmin} />
          </Form.Item>
          <Form.Item name="transport" label={t('mcp.colTransport', { defaultValue: '传输' })} rules={[{ required: true }]}>
            <Select
              disabled={!isWorkspaceAdmin}
              options={[
                { value: 'STDIO', label: 'STDIO' },
                { value: 'SSE', label: 'SSE' },
                { value: 'STREAMABLE_HTTP', label: 'Streamable HTTP' },
              ]}
            />
          </Form.Item>
          {transport === 'STDIO' ? (
            <>
              <Form.Item name="command" label="command" rules={[{ required: true }]}>
                <Input allowClear disabled={!isWorkspaceAdmin} />
              </Form.Item>
              <Form.Item name="args" label="args (one per line)">
                <Input.TextArea rows={3} allowClear disabled={!isWorkspaceAdmin} />
              </Form.Item>
              <Form.Item name="cwd" label="cwd">
                <Input allowClear disabled={!isWorkspaceAdmin} />
              </Form.Item>
              <Form.Item name="envJson" label="env (JSON object)">
                <Input.TextArea rows={3} placeholder='{"KEY":"value"}' disabled={!isWorkspaceAdmin} />
              </Form.Item>
            </>
          ) : (
            <>
              <Form.Item name="url" label="url" rules={[{ required: true }]}>
                <Input allowClear disabled={!isWorkspaceAdmin} />
              </Form.Item>
              <Form.Item name="headersJson" label="headers (JSON object)">
                <Input.TextArea rows={3} placeholder='{"Authorization":"Bearer ..."}' disabled={!isWorkspaceAdmin} />
              </Form.Item>
            </>
          )}
          <Form.Item name="enabled" label={t('mcp.colEnabled', { defaultValue: '启用' })} valuePropName="checked">
            <Switch disabled={!isWorkspaceAdmin} />
          </Form.Item>
          <Form.Item name="remark" label={t('common.remark', { defaultValue: '备注' })}>
            <Input allowClear disabled={!isWorkspaceAdmin} />
          </Form.Item>
          {editingClient?.has_secrets && !clientForm.getFieldValue('envJson') && !clientForm.getFieldValue('headersJson') ? (
            <Alert
              type="info"
              showIcon
              message={t('mcp.secretsKeptHint', {
                defaultValue: '密钥已保存；留空 env/headers 将沿用原值。',
              })}
            />
          ) : null}
          {!editingClient ? (
            <Alert
              type="warning"
              showIcon
              message={t('mcp.testBeforeSave', { defaultValue: '保存前将自动验证连通性' })}
            />
          ) : null}
        </Form>
      </Drawer>

      <Drawer
        title={
          editingServer
            ? t('mcp.editServer', { defaultValue: '编辑 MCP 服务端' })
            : t('mcp.addServer', { defaultValue: '新增服务端' })
        }
        open={serverDrawerOpen}
        width={520}
        onClose={() => setServerDrawerOpen(false)}
        extra={
          isWorkspaceAdmin ? (
            <Button
              type="primary"
              loading={saveServerMutation.isPending}
              onClick={() => void serverForm.submit()}
            >
              {t('common.save', { defaultValue: '保存' })}
            </Button>
          ) : null
        }
      >
        <Form form={serverForm} layout="vertical" onFinish={(v) => saveServerMutation.mutate(v)}>
          <Form.Item name="name" label={t('mcp.colName', { defaultValue: '名称' })} rules={[{ required: true }]}>
            <Input allowClear disabled={!isWorkspaceAdmin} />
          </Form.Item>
          <Form.Item name="slug" label="slug" rules={[{ required: true }]}>
            <Input allowClear placeholder="my-workspace-tools" disabled={!isWorkspaceAdmin} />
          </Form.Item>
          <Form.Item name="auth_type" label={t('mcp.colAuth', { defaultValue: '鉴权' })}>
            <Select
              disabled={!isWorkspaceAdmin}
              options={[
                { value: 'NONE', label: 'NONE' },
                { value: 'BEARER', label: 'BEARER' },
                { value: 'API_KEY', label: 'API_KEY' },
              ]}
            />
          </Form.Item>
          <Form.Item name="auth_secret" label="auth_secret">
            <Input.Password allowClear disabled={!isWorkspaceAdmin} />
          </Form.Item>
          <Form.Item
            name="include_all_builtin"
            label={t('mcp.exposeAllBuiltin', { defaultValue: '暴露全部内置 Skills' })}
            valuePropName="checked"
          >
            <Switch disabled={!isWorkspaceAdmin} />
          </Form.Item>
          {!includeAllBuiltin ? (
            <Form.Item name="builtin_skills" label={t('mcp.exposeBuiltinSkills', { defaultValue: '选择内置 Skills' })}>
              <Select
                mode="multiple"
                allowClear
                disabled={!isWorkspaceAdmin}
                options={skillOptions}
                placeholder={t('mcp.selectSkills', { defaultValue: '选择要暴露的技能' })}
              />
            </Form.Item>
          ) : null}
          <Form.Item
            name="include_all_clients"
            label={t('mcp.exposeAllClients', { defaultValue: '暴露全部 MCP 客户端' })}
            valuePropName="checked"
          >
            <Switch disabled={!isWorkspaceAdmin} />
          </Form.Item>
          {!includeAllClients ? (
            <Form.Item name="mcp_client_ids" label={t('mcp.exposeMcpClients', { defaultValue: '选择 MCP 客户端' })}>
              <Select
                mode="multiple"
                allowClear
                disabled={!isWorkspaceAdmin}
                options={clientOptions}
                placeholder={t('mcp.selectClients', { defaultValue: '选择要代理的客户端' })}
              />
            </Form.Item>
          ) : null}
          <Form.Item name="enabled" label={t('mcp.colEnabled', { defaultValue: '启用' })} valuePropName="checked">
            <Switch disabled={!isWorkspaceAdmin} />
          </Form.Item>
          <Form.Item name="remark" label={t('common.remark', { defaultValue: '备注' })}>
            <Input allowClear disabled={!isWorkspaceAdmin} />
          </Form.Item>
        </Form>
      </Drawer>

      <McpToolExplorerModal
        open={explorerClient != null}
        client={explorerClient}
        workspaceId={workspaceId}
        onClose={() => setExplorerClient(null)}
      />
    </div>
  )
}
