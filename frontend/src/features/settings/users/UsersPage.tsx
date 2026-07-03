import { DeleteOutlined, EditOutlined, PlusOutlined, UserDeleteOutlined } from '@ant-design/icons'
import {
  Alert,
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
  Tooltip,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  createUser,
  deleteUserAccount,
  getUser,
  getUserListCapabilities,
  getUserTenantAdmin,
  listTenantWorkspaceUsers,
  listUserAssignableRoles,
  listUsers,
  patchUser,
  putUserTenantAdmin,
  removeUserMembership,
  type SysUserCreateBody,
  type SysUserListCapabilities,
  type SysUserListItem,
  type SysUserListParams,
  type SysUserPatchBody,
} from '@/api/users'
import {
  listTenants,
  listWorkspaces,
  type SysTenantListItem,
  type SysWorkspaceListItem,
} from '@/api/tenants'
import { ApiError } from '@/api/client'
import { replaceWorkspaceRoleGrants } from '@/api/grants'
import { useAuth } from '@/app/AuthContext'
import { PermGuard, useCanManageUsers } from '@/components/PermGuard'
import { notifyMenuNavRefresh } from '@/app/menuNavRefresh'
import { resolveApiErrorMessage, showAppError, useAppMessage } from '@/app/useAppMessage'
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'
import { UserFormDrawer, type UserFormValues, type UserScope } from './UserFormDrawer'
import './UsersPage.css'

/** Horizontal scroll width for the users table. */
const USERS_TABLE_SCROLL_X = 1280

/** Gutter subtracted from wrap height to compute table body scroll.y. */
const USERS_TABLE_SCROLL_GUTTER_PX = 48

type FilterFormValues = {
  email?: string
  nickname?: string
  phone?: string
  status?: 'true' | 'false'
  membership_role?: string
  role_id?: string
}

/** Format ISO timestamp for table display. */
function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString(undefined, { hour12: false }) : '—'
}

/** Map filter form values to list API params. */
function toListParams(values: FilterFormValues): SysUserListParams {
  return {
    email: values.email?.trim() || undefined,
    nickname: values.nickname?.trim() || undefined,
    phone: values.phone?.trim() || undefined,
    status: values.status == null ? undefined : values.status === 'true',
    membership_role: values.membership_role || undefined,
    role_id: values.role_id || undefined,
  }
}

/** Workspace user management list with filters and member drawer. */
export function UsersPage() {
  const { t } = useTranslation()
  const messageApi = useAppMessage()
  const { workspaceId, userId, isSuperAdmin, isTenantAdmin, isWorkspaceAdmin, tenantId } =
    useAuth()
  const canManageUsers = useCanManageUsers()
  const useGrantApiForRoles =
    Boolean(tenantId) && (isSuperAdmin || isTenantAdmin || isWorkspaceAdmin)
  const tableWrapRef = useRef<HTMLDivElement | null>(null)
  const [tableBodyScrollY, setTableBodyScrollY] = useState(320)
  const [filterForm] = Form.useForm<FilterFormValues>()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [filters, setFilters] = useState<SysUserListParams>({})
  const [refreshTick, setRefreshTick] = useState(0)
  const [forbidden, setForbidden] = useState(false)
  const [capabilities, setCapabilities] = useState<SysUserListCapabilities | null>(null)
  const [filterTenantId, setFilterTenantId] = useState<string | null>(null)
  const [filterWorkspaceId, setFilterWorkspaceId] = useState<string | null>(null)
  const [tenants, setTenants] = useState<SysTenantListItem[]>([])
  const [filterWorkspaces, setFilterWorkspaces] = useState<SysWorkspaceListItem[]>([])
  const [formWorkspaces, setFormWorkspaces] = useState<SysWorkspaceListItem[]>([])
  const [formWorkspacesLoading, setFormWorkspacesLoading] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerTitle, setDrawerTitle] = useState('')
  const [drawerMode, setDrawerMode] = useState<'create' | 'edit'>('create')
  const [submitting, setSubmitting] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingWorkspaceId, setEditingWorkspaceId] = useState<string | null>(null)
  const [initialForm, setInitialForm] = useState<UserFormValues | null>(null)
  const [initialScope, setInitialScope] = useState<UserScope | null>(null)

  useEffect(() => {
    void getUserListCapabilities().then((caps) => {
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

  const loadFormWorkspaces = useCallback(async (tenantIdForForm: string) => {
    const page = await listWorkspaces(tenantIdForForm, { page_size: 100 })
    setFormWorkspaces(page.items)
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

  useEffect(() => {
    if (!capabilities?.can_pick_workspace || filterWorkspaces.length === 0) return
    if (
      filterWorkspaceId != null &&
      filterWorkspaces.some((w) => w.id === filterWorkspaceId)
    ) {
      return
    }
    const preferred =
      capabilities.default_filter_workspace_id &&
      filterWorkspaces.some((w) => w.id === capabilities.default_filter_workspace_id)
        ? capabilities.default_filter_workspace_id
        : filterWorkspaces[0].id
    setFilterWorkspaceId(preferred)
  }, [capabilities, filterWorkspaces, filterWorkspaceId])

  const effectiveTenantId = useMemo(() => {
    if (!capabilities) return null
    if (capabilities.can_pick_tenant) return filterTenantId
    return capabilities.fixed_tenant_id ?? tenantId
  }, [capabilities, filterTenantId, tenantId])

  const effectiveWorkspaceId = useMemo(() => {
    if (!capabilities) return null
    if (capabilities.can_pick_workspace) return filterWorkspaceId
    return workspaceId
  }, [capabilities, filterWorkspaceId, workspaceId])

  const rolesMetaQuery = useQuery({
    queryKey: ['users-meta-roles', effectiveWorkspaceId ?? workspaceId],
    queryFn: () => listUserAssignableRoles((effectiveWorkspaceId ?? workspaceId)!),
    enabled: Boolean(effectiveWorkspaceId ?? workspaceId),
  })

  const listQuery = useQuery({
    queryKey: [
      'users',
      effectiveTenantId,
      effectiveWorkspaceId,
      page,
      pageSize,
      filters,
      refreshTick,
      capabilities?.can_pick_workspace,
    ],
    queryFn: async () => {
      setForbidden(false)
      try {
        if (
          capabilities?.can_pick_workspace &&
          effectiveTenantId &&
          effectiveWorkspaceId
        ) {
          return await listTenantWorkspaceUsers(effectiveTenantId, {
            ...filters,
            workspace_id: effectiveWorkspaceId,
            page,
            page_size: pageSize,
          })
        }
        return await listUsers(workspaceId!, { ...filters, page, page_size: pageSize })
      } catch (e) {
        if (e instanceof ApiError && e.code === 'auth.forbidden') {
          setForbidden(true)
          return { items: [], total: 0, page: 1, page_size: pageSize }
        }
        throw e
      }
    },
    enabled: capabilities
      ? capabilities.can_pick_workspace
        ? Boolean(effectiveTenantId && effectiveWorkspaceId)
        : Boolean(workspaceId)
      : false,
  })

  const reloadList = useCallback(() => {
    setRefreshTick((v) => v + 1)
  }, [])

  useLayoutEffect(() => {
    const wrap = tableWrapRef.current
    if (wrap == null) return
    const measure = () => {
      const h = wrap.getBoundingClientRect().height
      setTableBodyScrollY(Math.max(120, Math.floor(h - USERS_TABLE_SCROLL_GUTTER_PX)))
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(wrap)
    return () => ro.disconnect()
  }, [forbidden, listQuery.isLoading])

  const handleFilterTenantChange = useCallback((value: string | null) => {
    setFilterTenantId(value)
    setFilterWorkspaceId(null)
    setPage(1)
  }, [])

  const handleFormTenantChange = useCallback(
    async (tid: string) => {
      setFormWorkspaces([])
      setFormWorkspacesLoading(true)
      try {
        await loadFormWorkspaces(tid)
      } finally {
        setFormWorkspacesLoading(false)
      }
    },
    [loadFormWorkspaces],
  )

  const openCreate = useCallback(async () => {
    setDrawerMode('create')
    setEditingId(null)
    setEditingWorkspaceId(null)
    setInitialScope(null)

    const tid = effectiveTenantId
    const wid = effectiveWorkspaceId
    if (tid && capabilities?.can_pick_workspace) {
      setFormWorkspacesLoading(true)
      try {
        await loadFormWorkspaces(tid)
      } finally {
        setFormWorkspacesLoading(false)
      }
    } else {
      setFormWorkspaces([])
    }

    setInitialForm({
      email: '',
      password: '',
      nickname: '',
      phone: null,
      status: true,
      remark: null,
      membership_role: 'member',
      tenant_admin_role: 'member',
      department_item_id: null,
      role_ids: [],
      tenant_id: tid ?? undefined,
      workspace_id: wid ?? undefined,
    })
    setDrawerTitle(t('users.add'))
    setDrawerOpen(true)
  }, [t, effectiveTenantId, effectiveWorkspaceId, capabilities, loadFormWorkspaces])

  const openEdit = useCallback(
    async (row: SysUserListItem) => {
      const rowWorkspaceId = row.workspace_id ?? workspaceId
      if (!rowWorkspaceId) return
      try {
        const detail = await getUser(rowWorkspaceId, row.id)
        const scopeTenantId =
          detail.tenant_id ?? capabilities?.fixed_tenant_id ?? tenantId ?? null
        let tenantAdminRole: 'admin' | 'member' = 'member'
        if (capabilities?.can_edit_tenant_admin && scopeTenantId) {
          const status = await getUserTenantAdmin(scopeTenantId, detail.id)
          tenantAdminRole = status.is_tenant_admin ? 'admin' : 'member'
        }
        setDrawerMode('edit')
        setEditingId(detail.id)
        setEditingWorkspaceId(rowWorkspaceId)
        if (detail.tenant_id && detail.workspace_id) {
          setInitialScope({
            tenant_id: detail.tenant_id,
            tenant_name: detail.tenant_name ?? row.tenant_name ?? '',
            workspace_id: detail.workspace_id,
            workspace_name: detail.workspace_name ?? row.workspace_name ?? '',
          })
        } else {
          setInitialScope(null)
        }
        setInitialForm({
          email: detail.email,
          nickname: detail.nickname,
          phone: detail.phone,
          status: detail.status,
          remark: detail.remark,
          membership_role: detail.membership_role,
          tenant_admin_role: tenantAdminRole,
          department_item_id: detail.department_item_id,
          role_ids: detail.role_ids,
        })
        setDrawerTitle(t('users.edit'))
        setDrawerOpen(true)
      } catch (e) {
        showAppError(messageApi, t, e)
      }
    },
    [workspaceId, t, messageApi, capabilities, tenantId],
  )

  const handleSubmit = useCallback(
    async (
      values: SysUserCreateBody | Record<string, unknown>,
      context: { targetWorkspaceId: string; effectiveTenantId: string | null },
    ) => {
      const { targetWorkspaceId, effectiveTenantId: formTenantId } = context
      if (!targetWorkspaceId) return
      const listWorkspaceId = effectiveWorkspaceId ?? workspaceId
      const scopeTenantId = formTenantId ?? effectiveTenantId ?? tenantId
      setSubmitting(true)
      try {
        const raw = values as SysUserCreateBody &
          SysUserPatchBody & { tenant_admin_role?: 'admin' | 'member' }
        const roleIds = raw.role_ids ?? []
        const tenantAdminRole = raw.tenant_admin_role
        const profile = { ...raw } as SysUserCreateBody & SysUserPatchBody
        delete (profile as Record<string, unknown>).tenant_admin_role
        if (useGrantApiForRoles) {
          delete profile.role_ids
        }
        let savedUserId: string | null = null
        if (drawerMode === 'create') {
          const created = await createUser(targetWorkspaceId, profile as SysUserCreateBody)
          savedUserId = created.id
          if (targetWorkspaceId !== listWorkspaceId) {
            messageApi.success(t('users.createSuccessOtherWorkspace'))
          } else {
            messageApi.success(t('users.createSuccess'))
          }
        } else if (editingId) {
          const editWsId = editingWorkspaceId ?? workspaceId
          if (!editWsId) return
          await patchUser(editWsId, editingId, profile as SysUserPatchBody)
          savedUserId = editingId
          messageApi.success(t('users.updateSuccess'))
        }
        if (
          capabilities?.can_edit_tenant_admin &&
          scopeTenantId &&
          tenantAdminRole != null &&
          savedUserId
        ) {
          const enabled = tenantAdminRole === 'admin'
          const initialEnabled = initialForm?.tenant_admin_role === 'admin'
          if (enabled !== initialEnabled) {
            await putUserTenantAdmin(scopeTenantId, savedUserId, enabled)
          }
        }
        const grantTenantId = scopeTenantId
        if (useGrantApiForRoles && grantTenantId && savedUserId) {
          if (drawerMode === 'create') {
            if (roleIds.length > 0) {
              await replaceWorkspaceRoleGrants(
                grantTenantId,
                targetWorkspaceId,
                savedUserId,
                roleIds,
              )
            }
          } else if (editingId) {
            const editWsId = editingWorkspaceId ?? workspaceId
            if (editWsId) {
              await replaceWorkspaceRoleGrants(grantTenantId, editWsId, savedUserId, roleIds)
            }
          }
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
      workspaceId,
      effectiveWorkspaceId,
      effectiveTenantId,
      drawerMode,
      editingId,
      editingWorkspaceId,
      messageApi,
      t,
      reloadList,
      useGrantApiForRoles,
      tenantId,
      capabilities,
      initialForm?.tenant_admin_role,
    ],
  )

  const handleRemoveMembership = useCallback(
    async (row: SysUserListItem) => {
      const rowWorkspaceId = row.workspace_id ?? workspaceId
      if (!rowWorkspaceId) return
      try {
        await removeUserMembership(rowWorkspaceId, row.id)
        messageApi.success(t('users.removeSuccess'))
        reloadList()
      } catch (e) {
        showAppError(messageApi, t, e)
      }
    },
    [workspaceId, messageApi, t, reloadList],
  )

  const handleDeleteAccount = useCallback(
    async (row: SysUserListItem) => {
      const rowWorkspaceId = row.workspace_id ?? workspaceId
      if (!rowWorkspaceId) return
      try {
        await deleteUserAccount(rowWorkspaceId, row.id)
        messageApi.success(t('users.deleteAccountSuccess'))
        reloadList()
      } catch (e) {
        showAppError(messageApi, t, e)
      }
    },
    [workspaceId, messageApi, t, reloadList],
  )

  const membershipTag = useCallback(
    (role: string) => {
      const map: Record<string, string> = {
        admin: t('users.membershipAdmin'),
        member: t('users.membershipMember'),
      }
      return <Tag>{map[role] ?? role}</Tag>
    },
    [t],
  )

  const columns: ColumnsType<SysUserListItem> = useMemo(
    () => [
      { title: t('users.email'), dataIndex: 'email', key: 'email', width: 200, ellipsis: true },
      { title: t('users.nickname'), dataIndex: 'nickname', key: 'nickname', width: 120 },
      {
        title: t('users.phone'),
        dataIndex: 'phone',
        key: 'phone',
        width: 130,
        render: (v: string | null) => v || '—',
      },
      {
        title: t('users.department'),
        dataIndex: 'department_name',
        key: 'department_name',
        width: 140,
        render: (v: string | null) => v || '—',
      },
      {
        title: t('users.membershipRole'),
        dataIndex: 'membership_role',
        key: 'membership_role',
        width: 100,
        render: (v: string) => membershipTag(v),
      },
      {
        title: t('users.roles'),
        dataIndex: 'role_names',
        key: 'role_names',
        width: 180,
        render: (names: string[]) =>
          names.length ? names.map((n) => <Tag key={n}>{n}</Tag>) : '—',
      },
      {
        title: t('users.status'),
        dataIndex: 'status',
        key: 'status',
        width: 80,
        render: (v: boolean) => (
          <Tag color={v ? 'success' : 'default'}>
            {v ? t('users.statusNormal') : t('users.statusDisabled')}
          </Tag>
        ),
      },
      {
        title: t('users.createAt'),
        dataIndex: 'created_at',
        key: 'created_at',
        width: 170,
        render: formatDateTime,
      },
      {
        title: t('users.actions'),
        key: 'actions',
        fixed: 'right',
        width: 220,
        render: (_, row) => {
          const isSelf = userId != null && row.id === userId
          if (!canManageUsers) return null
          return (
            <PermGuard perm="tenant:member:manage">
              <Space size="small">
                <Tooltip title={t('users.edit')}>
                  <Button
                    type="link"
                    size="small"
                    icon={<EditOutlined />}
                    onClick={() => void openEdit(row)}
                  />
                </Tooltip>
                {!isSelf ? (
                  <Popconfirm
                    title={t('users.removeMembershipConfirm', { name: row.nickname })}
                    description={t('users.removeMembershipDesc')}
                    onConfirm={() => void handleRemoveMembership(row)}
                  >
                    <Tooltip title={t('users.removeMembership')}>
                      <Button type="link" size="small" icon={<UserDeleteOutlined />} />
                    </Tooltip>
                  </Popconfirm>
                ) : null}
                {!isSelf && row.can_hard_delete ? (
                  <Popconfirm
                    title={t('users.deleteAccountConfirm', { name: row.nickname })}
                    description={t('users.deleteAccountDesc')}
                    onConfirm={() => void handleDeleteAccount(row)}
                  >
                    <Tooltip title={t('users.deleteAccount')}>
                      <Button type="link" size="small" danger icon={<DeleteOutlined />} />
                    </Tooltip>
                  </Popconfirm>
                ) : null}
              </Space>
            </PermGuard>
          )
        },
      },
    ],
    [
      t,
      canManageUsers,
      membershipTag,
      openEdit,
      handleRemoveMembership,
      handleDeleteAccount,
      userId,
    ],
  )

  if (!workspaceId) {
    return <Result status="warning" title={t('users.noWorkspace')} />
  }

  if (forbidden) {
    return (
      <Result
        status="403"
        title={t('users.forbiddenTitle')}
        subTitle={t('users.forbiddenDesc')}
      />
    )
  }

  const showScopeFilters =
    capabilities?.can_pick_tenant === true || capabilities?.can_pick_workspace === true

  return (
    <div className="minerva-users-page">
      <Card className="minerva-users-page__card" bordered={false}>
        <div className="minerva-users-page__header">
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
                      allowClear={false}
                      placeholder={t('users.tenantPlaceholder')}
                      style={{ width: 160 }}
                      value={filterTenantId ?? undefined}
                      onChange={(value) => handleFilterTenantChange(value ?? null)}
                      options={tenants.map((row) => ({
                        value: row.id,
                        label: row.name,
                      }))}
                    />
                  </Form.Item>
                ) : null}
                {capabilities?.can_pick_workspace ? (
                  <Form.Item>
                    <Select
                      allowClear={false}
                      placeholder={t('users.workspacePlaceholder')}
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
            <Form.Item name="membership_role">
              <Select
                allowClear
                placeholder={t('users.membershipRole')}
                style={{ width: 120 }}
                options={[
                  { value: 'admin', label: t('users.membershipAdmin') },
                  { value: 'member', label: t('users.membershipMember') },
                ]}
              />
            </Form.Item>
            <Form.Item name="role_id">
              <Select
                allowClear
                placeholder={t('users.roles')}
                style={{ width: 140 }}
                options={(rolesMetaQuery.data ?? []).map((r) => ({
                  value: r.id,
                  label: r.role_name,
                }))}
              />
            </Form.Item>
            <Form.Item name="status">
              <Select
                allowClear
                placeholder={t('users.status')}
                style={{ width: 110 }}
                options={[
                  { value: 'true', label: t('users.statusNormal') },
                  { value: 'false', label: t('users.statusDisabled') },
                ]}
              />
            </Form.Item>
            <Form.Item name="email">
              <Input allowClear placeholder={t('users.emailPlaceholder')} style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="nickname">
              <Input
                allowClear
                placeholder={t('users.nicknamePlaceholder')}
                style={{ width: 120 }}
              />
            </Form.Item>
            <Form.Item name="phone">
              <Input allowClear placeholder={t('users.phonePlaceholder')} style={{ width: 130 }} />
            </Form.Item>
            <Form.Item>
              <Space>
                <Button type="primary" htmlType="submit">
                  {t('users.search')}
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
                  {t('users.reset')}
                </Button>
                <PermGuard perm="tenant:member:manage">
                  <Button
                    type="primary"
                    icon={<PlusOutlined />}
                    onClick={() => void openCreate()}
                  >
                    {t('users.add')}
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
                  ? resolveApiErrorMessage(t, listQuery.error)
                  : t('common.error')
              }
            />
          )}
        </div>
        <div ref={tableWrapRef} className="minerva-users-page__table-wrap">
          <Table<SysUserListItem>
            className="minerva-card-table-scroll-ocr"
            rowKey={(row) => `${row.id}-${row.workspace_id ?? ''}`}
            loading={listQuery.isLoading}
            columns={columns}
            dataSource={listQuery.data?.items ?? []}
            scroll={{ x: USERS_TABLE_SCROLL_X, y: tableBodyScrollY }}
            sticky
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
      <UserFormDrawer
        open={drawerOpen}
        title={drawerTitle}
        submitting={submitting}
        mode={drawerMode}
        listCapabilities={capabilities}
        pageWorkspaceId={effectiveWorkspaceId ?? workspaceId}
        initial={initialForm}
        initialScope={initialScope}
        tenants={tenants}
        workspaces={formWorkspaces}
        workspacesLoading={formWorkspacesLoading}
        onTenantChange={handleFormTenantChange}
        onClose={() => setDrawerOpen(false)}
        onSubmit={handleSubmit}
      />
    </div>
  )
}
