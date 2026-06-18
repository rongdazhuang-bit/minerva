import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons'
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
import {
  createMcpClient,
  createMcpServer,
  deleteMcpClient,
  deleteMcpServer,
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
}

/** Workspace MCP client/server management (test-before-save for clients). */
export function AgentMcpPage() {
  const { t } = useTranslation()
  const messageApi = useAppMessage()
  const { workspaceId } = useAuth()
  const queryClient = useQueryClient()
  const [clientDrawerOpen, setClientDrawerOpen] = useState(false)
  const [serverDrawerOpen, setServerDrawerOpen] = useState(false)
  const [editingClient, setEditingClient] = useState<McpClientListItem | null>(null)
  const [editingServer, setEditingServer] = useState<McpServerListItem | null>(null)
  const [clientForm] = Form.useForm<ClientFormValues>()
  const [serverForm] = Form.useForm<ServerFormValues>()
  const transport = Form.useWatch('transport', clientForm) as McpTransport | undefined

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

  const invalidate = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['mcp-clients', workspaceId] })
    void queryClient.invalidateQueries({ queryKey: ['mcp-servers', workspaceId] })
  }, [queryClient, workspaceId])

  const buildClientPayload = (values: ClientFormValues) => {
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
    return {
      name: values.name.trim(),
      transport: transportVal,
      config,
      secrets,
      enabled: values.enabled,
      remark: values.remark?.trim() || null,
    }
  }

  const saveClientMutation = useMutation({
    mutationFn: async (values: ClientFormValues) => {
      const body = buildClientPayload(values)
      const test = await testMcpClient(workspaceId!, {
        transport: body.transport,
        config: body.config,
        secrets: body.secrets,
      })
      if (!test.ok) {
        throw new Error(test.error_message || t('mcp.testFailed', { defaultValue: '连通性测试失败' }))
      }
      if (editingClient) {
        return patchMcpClient(workspaceId!, editingClient.id, body)
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
          builtin_skills: [],
          mcp_client_ids: [],
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
        render: (_, row) => (
          <Space>
            <Button
              type="link"
              icon={<EditOutlined />}
              onClick={() => {
                setEditingClient(row)
                clientForm.setFieldsValue({
                  name: row.name,
                  transport: row.transport,
                  enabled: row.enabled,
                  remark: row.remark ?? undefined,
                })
                setClientDrawerOpen(true)
              }}
            />
            <Popconfirm
              title={t('mcp.deleteClientConfirm', { defaultValue: '确定删除此 MCP 客户端？' })}
              onConfirm={async () => {
                await deleteMcpClient(workspaceId!, row.id)
                invalidate()
              }}
            >
              <Button type="link" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          </Space>
        ),
      },
    ],
    [clientForm, invalidate, t, workspaceId],
  )

  const serverColumns: ColumnsType<McpServerListItem> = useMemo(
    () => [
      { title: t('mcp.colName', { defaultValue: '名称' }), dataIndex: 'name' },
      { title: 'slug', dataIndex: 'slug' },
      { title: t('mcp.colAuth', { defaultValue: '鉴权' }), dataIndex: 'auth_type' },
      {
        title: t('common.actions', { defaultValue: '操作' }),
        render: (_, row) => (
          <Space>
            <Button
              type="link"
              icon={<EditOutlined />}
              onClick={() => {
                setEditingServer(row)
                serverForm.setFieldsValue({
                  name: row.name,
                  slug: row.slug,
                  enabled: row.enabled,
                  auth_type: row.auth_type as ServerFormValues['auth_type'],
                  remark: row.remark ?? undefined,
                  include_all_builtin: Boolean(row.exposure?.include_all_builtin),
                  include_all_clients: Boolean(row.exposure?.include_all_clients),
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
      },
    ],
    [invalidate, serverForm, t, workspaceId],
  )

  if (!workspaceId) {
    return <Alert type="warning" message={t('agents.noWorkspace')} />
  }

  return (
    <div className="minerva-agent-mcp-page">
      <Card title={t('nav.agentsMcp', { defaultValue: 'MCP' })} variant="borderless">
        <Tabs
          items={[
            {
              key: 'clients',
              label: t('mcp.clientsTab', { defaultValue: 'MCP 客户端' }),
              children: (
                <>
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
                  <Table
                    rowKey="id"
                    loading={clientsLoading}
                    columns={clientColumns}
                    dataSource={clients}
                    pagination={{ pageSize: 10 }}
                  />
                </>
              ),
            },
            {
              key: 'servers',
              label: t('mcp.serversTab', { defaultValue: 'MCP 服务端' }),
              children: (
                <>
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
                        })
                        setServerDrawerOpen(true)
                      }}
                    >
                      {t('mcp.addServer', { defaultValue: '新增服务端' })}
                    </Button>
                  </div>
                  <Table
                    rowKey="id"
                    loading={serversLoading}
                    columns={serverColumns}
                    dataSource={servers}
                    pagination={{ pageSize: 10 }}
                  />
                </>
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
          <Button
            type="primary"
            loading={saveClientMutation.isPending}
            onClick={() => void clientForm.submit()}
          >
            {t('common.save', { defaultValue: '保存' })}
          </Button>
        }
      >
        <Form form={clientForm} layout="vertical" onFinish={(v) => saveClientMutation.mutate(v)}>
          <Form.Item name="name" label={t('mcp.colName', { defaultValue: '名称' })} rules={[{ required: true }]}>
            <Input allowClear />
          </Form.Item>
          <Form.Item name="transport" label={t('mcp.colTransport', { defaultValue: '传输' })} rules={[{ required: true }]}>
            <Select
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
                <Input allowClear />
              </Form.Item>
              <Form.Item name="args" label="args (one per line)">
                <Input.TextArea rows={3} allowClear />
              </Form.Item>
              <Form.Item name="cwd" label="cwd">
                <Input allowClear />
              </Form.Item>
              <Form.Item name="envJson" label="env (JSON object)">
                <Input.TextArea rows={3} placeholder='{"KEY":"value"}' />
              </Form.Item>
            </>
          ) : (
            <>
              <Form.Item name="url" label="url" rules={[{ required: true }]}>
                <Input allowClear />
              </Form.Item>
              <Form.Item name="headersJson" label="headers (JSON object)">
                <Input.TextArea rows={3} placeholder='{"Authorization":"Bearer ..."}' />
              </Form.Item>
            </>
          )}
          <Form.Item name="enabled" label={t('mcp.colEnabled', { defaultValue: '启用' })} valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="remark" label={t('common.remark', { defaultValue: '备注' })}>
            <Input allowClear />
          </Form.Item>
          <Alert
            type="warning"
            showIcon
            message={t('mcp.testBeforeSave', { defaultValue: '保存前将自动验证连通性' })}
          />
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
          <Button
            type="primary"
            loading={saveServerMutation.isPending}
            onClick={() => void serverForm.submit()}
          >
            {t('common.save', { defaultValue: '保存' })}
          </Button>
        }
      >
        <Form form={serverForm} layout="vertical" onFinish={(v) => saveServerMutation.mutate(v)}>
          <Form.Item name="name" label={t('mcp.colName', { defaultValue: '名称' })} rules={[{ required: true }]}>
            <Input allowClear />
          </Form.Item>
          <Form.Item name="slug" label="slug" rules={[{ required: true }]}>
            <Input allowClear placeholder="my-workspace-tools" />
          </Form.Item>
          <Form.Item name="auth_type" label={t('mcp.colAuth', { defaultValue: '鉴权' })}>
            <Select
              options={[
                { value: 'NONE', label: 'NONE' },
                { value: 'BEARER', label: 'BEARER' },
                { value: 'API_KEY', label: 'API_KEY' },
              ]}
            />
          </Form.Item>
          <Form.Item name="auth_secret" label="auth_secret">
            <Input.Password allowClear />
          </Form.Item>
          <Form.Item name="include_all_builtin" label={t('mcp.exposeAllBuiltin', { defaultValue: '暴露全部内置 Skills' })} valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="include_all_clients" label={t('mcp.exposeAllClients', { defaultValue: '暴露全部 MCP 客户端' })} valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="enabled" label={t('mcp.colEnabled', { defaultValue: '启用' })} valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="remark" label={t('common.remark', { defaultValue: '备注' })}>
            <Input allowClear />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  )
}
