import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons'
import {
  Button,
  Card,
  Form,
  Input,
  Popconfirm,
  Result,
  Select,
  Space,
  Table,
  Tag,
  Alert,
  Tooltip,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { SysMenuNode } from '@/api/menus'
import {
  createRole,
  deleteRole,
  getRole,
  getRoleCapabilities,
  listRoleMenuTree,
  listRolesForTenant,
  listRolesPlatform,
  patchRole,
  type SysRoleCapabilities,
  type SysRoleCreateBody,
  type SysRoleListItem,
  type SysRoleListParams,
  type SysRolePatchBody,
} from '@/api/roles'
import {
  listTenants,
  listWorkspaces,
  type SysTenantListItem,
  type SysWorkspaceListItem,
} from '@/api/tenants'
import { ApiError } from '@/api/client'
import { useAuth } from '@/app/AuthContext'
import { PermGuard } from '@/components/PermGuard'
import { notifyMenuNavRefresh } from '@/app/menuNavRefresh'
import { showAppError, useAppMessage } from '@/app/useAppMessage'
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'
import { RoleFormDrawer, type RoleFormValues, type RoleScope } from './RoleFormDrawer'
import './RolesPage.css'

type FilterFormValues = {
  role_name?: string
  status?: 'true' | 'false'
}

/** Format ISO timestamp for table display. */
function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString(undefined, { hour12: false }) : '—'
}

/** Map filter form values to list API params. */
function toListParams(values: FilterFormValues): SysRoleListParams {
  return {
    role_name: values.role_name?.trim() || undefined,
    status:
      values.status == null ? undefined : values.status === 'true',
  }
}

/** Tenant-scoped role management list with filters and permission drawer. */
export function RolesPage() {
  const { t } = useTranslation()
  const messageApi = useAppMessage()
  const { tenantId, workspaceId } = useAuth()
  const [filterForm] = Form.useForm<FilterFormValues>()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [filters, setFilters] = useState<SysRoleListParams>({})
  const [refreshTick, setRefreshTick] = useState(0)
  const [forbidden, setForbidden] = useState(false)
  const [capabilities, setCapabilities] = useState<SysRoleCapabilities | null>(null)
  const [filterTenantId, setFilterTenantId] = useState<string | null>(null)
  const [filterWorkspaceId, setFilterWorkspaceId] = useState<string | null>(null)
  const [tenants, setTenants] = useState<SysTenantListItem[]>([])
  const [filterWorkspaces, setFilterWorkspaces] = useState<SysWorkspaceListItem[]>([])
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerTitle, setDrawerTitle] = useState('')
  const [drawerMode, setDrawerMode] = useState<'create' | 'edit'>('create')
  const [submitting, setSubmitting] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingTenantId, setEditingTenantId] = useState<string | null>(null)
  const [initialForm, setInitialForm] = useState<RoleFormValues | null>(null)
  const [initialScope, setInitialScope] = useState<RoleScope | null>(null)
  const [initialMenuIds, setInitialMenuIds] = useState<string[]>([])
  const [menuTree, setMenuTree] = useState<SysMenuNode[]>([])
  const [createTenantId, setCreateTenantId] = useState<string | null>(null)
  const [createWorkspaces, setCreateWorkspaces] = useState<SysWorkspaceListItem[]>([])
  const [metaLoading, setMetaLoading] = useState(false)

  useEffect(() => {
    void getRoleCapabilities().then((caps) => {
      setCapabilities(caps)
      setFilterTenantId(caps.default_filter_tenant_id)
      setFilterWorkspaceId(caps.default_filter_workspace_id)
    })
  }, [])

  useEffect(() => {
    if (!capabilities?.can_pick_tenant) return
    void listTenants({ page_size: 100 }).then((page) => {
      setTenants(page.items)
    })
  }, [capabilities?.can_pick_tenant])

  const loadFilterWorkspaces = useCallback(async (tenantIdForList: string) => {
    const page = await listWorkspaces(tenantIdForList, { page_size: 100 })
    setFilterWorkspaces(page.items)
    return page.items
  }, [])

  useEffect(() => {
    if (!capabilities?.can_pick_workspace) return
    const tid = filterTenantId ?? capabilities.fixed_tenant_id
    if (!tid) {
      setFilterWorkspaces([])
      return
    }
    void loadFilterWorkspaces(tid)
  }, [capabilities, filterTenantId, loadFilterWorkspaces])

  const effectiveTenantId = useMemo(() => {
    if (!capabilities) return null
    if (capabilities.can_pick_tenant) {
      return filterTenantId
    }
    return capabilities.fixed_tenant_id ?? tenantId
  }, [capabilities, filterTenantId, tenantId])

  const effectiveWorkspaceId = useMemo(() => {
    if (!capabilities) return null
    if (capabilities.can_pick_workspace) {
      return filterWorkspaceId
    }
    return workspaceId
  }, [capabilities, filterWorkspaceId, workspaceId])

  const listEnabled = useMemo(() => {
    if (!capabilities) return false
    if (capabilities.can_pick_tenant || capabilities.can_pick_workspace) return true
    return Boolean(tenantId && workspaceId)
  }, [capabilities, tenantId, workspaceId])

  const listQuery = useQuery({
    queryKey: [
      'roles',
      effectiveTenantId,
      effectiveWorkspaceId,
      page,
      pageSize,
      filters,
      refreshTick,
      capabilities?.can_pick_tenant,
    ],
    queryFn: async () => {
      setForbidden(false)
      try {
        const params: SysRoleListParams = {
          ...filters,
          page,
          page_size: pageSize,
          workspace_id: effectiveWorkspaceId ?? undefined,
        }
        if (capabilities?.can_pick_tenant && !effectiveTenantId) {
          return await listRolesPlatform({ ...params, tenant_id: undefined })
        }
        const tid = effectiveTenantId ?? capabilities?.fixed_tenant_id ?? tenantId
        if (!tid) throw new Error('tenant required')
        return await listRolesForTenant(tid, params)
      } catch (e) {
        if (e instanceof ApiError && e.code === 'auth.forbidden') {
          setForbidden(true)
          return { items: [], total: 0, page: 1, page_size: pageSize }
        }
        throw e
      }
    },
    enabled: listEnabled,
  })

  const reloadList = useCallback(() => {
    setRefreshTick((v) => v + 1)
  }, [])

  const loadMenuTree = useCallback(async () => {
    const tree = await listRoleMenuTree()
    setMenuTree(tree)
    return tree
  }, [])

  const loadCreateWorkspaces = useCallback(async (tenantIdForCreate: string) => {
    const page = await listWorkspaces(tenantIdForCreate, { page_size: 100 })
    setCreateWorkspaces(page.items)
    return page.items
  }, [])

  const handleCreateTenantChange = useCallback(
    async (tid: string) => {
      setCreateTenantId(tid)
      await loadCreateWorkspaces(tid)
    },
    [loadCreateWorkspaces],
  )

  const openCreate = useCallback(async () => {
    setMetaLoading(true)
    try {
      await loadMenuTree()
      setDrawerMode('create')
      setEditingId(null)
      setEditingTenantId(null)
      setInitialScope(null)

      let initialTenantId: string | null = null
      if (capabilities?.can_pick_tenant) {
        const tenantRows =
          tenants.length > 0 ? tenants : (await listTenants({ page_size: 100 })).items
        if (tenantRows.length > 0 && tenants.length === 0) {
          setTenants(tenantRows)
        }
        initialTenantId = tenantRows[0]?.id ?? null
      } else {
        initialTenantId = capabilities?.fixed_tenant_id ?? tenantId
      }

      setCreateTenantId(initialTenantId)
      let wsRows: SysWorkspaceListItem[] = []
      if (initialTenantId) {
        wsRows = await loadCreateWorkspaces(initialTenantId)
      }

      setInitialForm({
        role_name: '',
        role_key: '',
        role_sort: 0,
        status: true,
        remark: null,
        tenant_id: initialTenantId ?? undefined,
        workspace_id: wsRows[0]?.id,
      })
      setInitialMenuIds([])
      setDrawerTitle(t('roles.add'))
      setDrawerOpen(true)
    } catch (e) {
      showAppError(messageApi, t, e)
    } finally {
      setMetaLoading(false)
    }
  }, [
    loadMenuTree,
    capabilities,
    tenants,
    tenantId,
    loadCreateWorkspaces,
    t,
    messageApi,
  ])

  const openEdit = useCallback(
    async (row: SysRoleListItem) => {
      setMetaLoading(true)
      try {
        await loadMenuTree()
        const detail = await getRole(row.tenant_id, row.id)
        setDrawerMode('edit')
        setEditingId(row.id)
        setEditingTenantId(row.tenant_id)
        setInitialScope({
          tenant_id: row.tenant_id,
          tenant_name: row.tenant_name,
          workspace_id: row.workspace_id,
          workspace_name: row.workspace_name,
        })
        setInitialForm({
          role_name: detail.role_name,
          role_key: detail.role_key,
          role_sort: detail.role_sort,
          status: detail.status,
          remark: detail.remark,
        })
        setInitialMenuIds(detail.menu_ids)
        setDrawerTitle(t('roles.edit'))
        setDrawerOpen(true)
      } catch (e) {
        showAppError(messageApi, t, e)
      } finally {
        setMetaLoading(false)
      }
    },
    [loadMenuTree, t, messageApi],
  )

  const handleSubmit = useCallback(
    async (
      body: SysRoleCreateBody | SysRolePatchBody,
      context?: { tenantId?: string },
    ) => {
      setSubmitting(true)
      try {
        if (drawerMode === 'edit' && editingId && editingTenantId) {
          await patchRole(editingTenantId, editingId, body)
          messageApi.success(t('roles.updateSuccess'))
        } else {
          const tid =
            context?.tenantId ??
            createTenantId ??
            capabilities?.fixed_tenant_id ??
            tenantId
          if (!tid) return
          await createRole(tid, body as SysRoleCreateBody)
          messageApi.success(t('roles.createSuccess'))
        }
        setDrawerOpen(false)
        reloadList()
        notifyMenuNavRefresh()
      } catch (e) {
        showAppError(messageApi, t, e)
      } finally {
        setSubmitting(false)
      }
    },
    [
      drawerMode,
      editingId,
      editingTenantId,
      createTenantId,
      capabilities,
      tenantId,
      messageApi,
      t,
      reloadList,
    ],
  )

  const handleDelete = useCallback(
    async (row: SysRoleListItem) => {
      try {
        await deleteRole(row.tenant_id, row.id)
        messageApi.success(t('roles.deleteSuccess'))
        reloadList()
      } catch (e) {
        showAppError(messageApi, t, e)
      }
    },
    [messageApi, t, reloadList],
  )

  const handleFilterTenantChange = useCallback(
    (value: string | null) => {
      setFilterTenantId(value)
      setFilterWorkspaceId(null)
      setPage(1)
    },
    [],
  )

  const columns: ColumnsType<SysRoleListItem> = useMemo(
    () => [
      { title: t('roles.tenant'), dataIndex: 'tenant_name', width: 140, ellipsis: true },
      {
        title: t('roles.workspace'),
        dataIndex: 'workspace_name',
        width: 140,
        ellipsis: true,
      },
      { title: t('roles.name'), dataIndex: 'role_name', width: 160 },
      {
        title: t('roles.roleKey'),
        dataIndex: 'role_key',
        width: 200,
      },
      { title: t('roles.sort'), dataIndex: 'role_sort', width: 80 },
      {
        title: t('roles.status'),
        dataIndex: 'status',
        width: 100,
        render: (status: boolean) => (
          <Tag color={status ? 'success' : 'default'}>
            {status ? t('roles.statusNormal') : t('roles.statusDisabled')}
          </Tag>
        ),
      },
      {
        title: t('roles.createAt'),
        dataIndex: 'create_at',
        width: 170,
        render: formatDateTime,
      },
      {
        title: t('roles.updateAt'),
        dataIndex: 'update_at',
        width: 170,
        render: formatDateTime,
      },
      {
        title: t('roles.actions'),
        key: 'actions',
        width: 88,
        fixed: 'right',
        render: (_, row) => (
          <PermGuard perm="tenant:role:manage">
            <Space size={2}>
              <Tooltip title={t('roles.edit')}>
                <Button
                  type="text"
                  size="small"
                  icon={<EditOutlined />}
                  onClick={() => void openEdit(row)}
                  aria-label={t('roles.edit')}
                />
              </Tooltip>
              <Tooltip title={t('roles.delete')}>
                <span>
                  <Popconfirm
                    title={t('roles.deleteConfirmTitle', { name: row.role_name })}
                    description={t('roles.deleteConfirmDesc')}
                    onConfirm={() => void handleDelete(row)}
                  >
                    <Button
                      type="text"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      aria-label={t('roles.delete')}
                    />
                  </Popconfirm>
                </span>
              </Tooltip>
            </Space>
          </PermGuard>
        ),
      },
    ],
    [t, openEdit, handleDelete],
  )

  if (forbidden) {
    return <Result status="403" title={t('roles.forbiddenTitle')} subTitle={t('roles.forbiddenDesc')} />
  }

  const showScopeFilters =
    capabilities?.can_pick_tenant === true || capabilities?.can_pick_workspace === true

  return (
    <div className="minerva-roles-page">
      <Card className="minerva-roles-page__card" bordered={false}>
        <div className="minerva-roles-page__header">
          <Form
            form={filterForm}
            layout="inline"
            onFinish={(values) => {
              setFilters(toListParams(values))
              setPage(1)
            }}
          >
            {showScopeFilters ? (
              <>
                {capabilities?.can_pick_tenant ? (
                  <Form.Item>
                    <Select
                      allowClear
                      placeholder={t('roles.allTenants')}
                      style={{ width: 160 }}
                      value={filterTenantId ?? undefined}
                      onChange={(value) => handleFilterTenantChange(value ?? null)}
                      options={tenants.map((row) => ({
                        value: row.id,
                        label: row.name,
                      }))}
                    />
                  </Form.Item>
                ) : capabilities?.fixed_tenant_name ? (
                  <Form.Item>
                    <Tag>{capabilities.fixed_tenant_name}</Tag>
                  </Form.Item>
                ) : null}
                {capabilities?.can_pick_workspace ? (
                  <Form.Item>
                    <Select
                      allowClear
                      placeholder={t('roles.allWorkspaces')}
                      style={{ width: 160 }}
                      value={filterWorkspaceId ?? undefined}
                      disabled={capabilities.can_pick_tenant && !filterTenantId}
                      onChange={(value) => {
                        setFilterWorkspaceId(value ?? null)
                        setPage(1)
                      }}
                      options={filterWorkspaces.map((row) => ({
                        value: row.id,
                        label: row.name,
                      }))}
                    />
                  </Form.Item>
                ) : null}
              </>
            ) : null}
            <Form.Item name="role_name">
              <Input allowClear placeholder={t('roles.roleNamePlaceholder')} style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="status">
              <Select
                allowClear
                placeholder={t('roles.status')}
                style={{ width: 120 }}
                options={[
                  { value: 'true', label: t('roles.statusNormal') },
                  { value: 'false', label: t('roles.statusDisabled') },
                ]}
              />
            </Form.Item>
            <Form.Item>
              <Space>
                <Button type="primary" htmlType="submit">
                  {t('roles.search')}
                </Button>
                <Button
                  onClick={() => {
                    filterForm.resetFields()
                    setFilters({})
                    setFilterTenantId(capabilities?.default_filter_tenant_id ?? null)
                    setFilterWorkspaceId(capabilities?.default_filter_workspace_id ?? null)
                    setPage(1)
                  }}
                >
                  {t('roles.reset')}
                </Button>
                <PermGuard perm="tenant:role:manage">
                  <Button type="primary" icon={<PlusOutlined />} onClick={() => void openCreate()}>
                    {t('roles.add')}
                  </Button>
                </PermGuard>
              </Space>
            </Form.Item>
          </Form>
          {listQuery.error != null && (
            <Alert
              type="error"
              showIcon
              style={{ marginTop: 12 }}
              message={
                listQuery.error instanceof ApiError
                  ? listQuery.error.message
                  : t('common.error')
              }
            />
          )}
        </div>
        <div className="minerva-roles-page__table-wrap">
          <Table<SysRoleListItem>
            className="minerva-card-table-scroll-ocr"
            rowKey="id"
            loading={listQuery.isLoading}
            columns={columns}
            dataSource={listQuery.data?.items ?? []}
            scroll={{ x: 1180 }}
            pagination={{
              current: page,
              pageSize,
              total: listQuery.data?.total ?? 0,
              showSizeChanger: true,
              onChange: (p, ps) => {
                setPage(p)
                setPageSize(ps)
              },
            }}
          />
        </div>
      </Card>
      <RoleFormDrawer
        open={drawerOpen}
        title={drawerTitle}
        submitting={submitting}
        mode={drawerMode}
        capabilities={capabilities}
        menuTree={menuTree}
        initial={initialForm}
        initialMenuIds={initialMenuIds}
        initialScope={initialScope}
        tenants={tenants}
        workspaces={createWorkspaces}
        onTenantChange={(tid) => void handleCreateTenantChange(tid)}
        metaLoading={metaLoading}
        onClose={() => setDrawerOpen(false)}
        onSubmit={handleSubmit}
      />
    </div>
  )
}
