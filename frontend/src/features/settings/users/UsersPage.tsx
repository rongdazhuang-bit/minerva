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
import { useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  createUser,
  deleteUserAccount,
  getUser,
  listUserAssignableRoles,
  listUsers,
  patchUser,
  removeUserMembership,
  type SysUserCreateBody,
  type SysUserListItem,
  type SysUserListParams,
  type SysUserPatchBody,
} from '@/api/users'
import { ApiError } from '@/api/client'
import { useAuth } from '@/app/AuthContext'
import { notifyMenuNavRefresh } from '@/app/menuNavRefresh'
import { resolveApiErrorMessage, showAppError, useAppMessage } from '@/app/useAppMessage'
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'
import { UserFormDrawer, type UserFormValues } from './UserFormDrawer'
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
    status:
      values.status == null ? undefined : values.status === 'true',
    membership_role: values.membership_role || undefined,
    role_id: values.role_id || undefined,
  }
}

/** Workspace user management list with filters and member drawer. */
export function UsersPage() {
  const { t } = useTranslation()
  const messageApi = useAppMessage()
  const { workspaceId, userId, isWorkspaceManager } = useAuth()
  const tableWrapRef = useRef<HTMLDivElement | null>(null)
  const [tableBodyScrollY, setTableBodyScrollY] = useState(320)
  const [filterForm] = Form.useForm<FilterFormValues>()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [filters, setFilters] = useState<SysUserListParams>({})
  const [refreshTick, setRefreshTick] = useState(0)
  const [forbidden, setForbidden] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerTitle, setDrawerTitle] = useState('')
  const [drawerMode, setDrawerMode] = useState<'create' | 'edit'>('create')
  const [submitting, setSubmitting] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [initialForm, setInitialForm] = useState<UserFormValues | null>(null)

  const rolesMetaQuery = useQuery({
    queryKey: ['users-meta-roles', workspaceId],
    queryFn: () => listUserAssignableRoles(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const listQuery = useQuery({
    queryKey: ['users', workspaceId, page, pageSize, filters, refreshTick],
    queryFn: async () => {
      setForbidden(false)
      try {
        return await listUsers(workspaceId!, { ...filters, page, page_size: pageSize })
      } catch (e) {
        if (e instanceof ApiError && e.code === 'auth.forbidden') {
          setForbidden(true)
          return { items: [], total: 0, page: 1, page_size: pageSize }
        }
        throw e
      }
    },
    enabled: Boolean(workspaceId),
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

  const openCreate = useCallback(() => {
    setDrawerMode('create')
    setEditingId(null)
    setInitialForm({
      email: '',
      password: '',
      nickname: '',
      phone: null,
      status: true,
      remark: null,
      membership_role: 'member',
      department_item_id: null,
      role_ids: [],
    })
    setDrawerTitle(t('users.add'))
    setDrawerOpen(true)
  }, [t])

  const openEdit = useCallback(
    async (row: SysUserListItem) => {
      if (!workspaceId) return
      try {
        const detail = await getUser(workspaceId, row.id)
        setDrawerMode('edit')
        setEditingId(detail.id)
        setInitialForm({
          email: detail.email,
          nickname: detail.nickname,
          phone: detail.phone,
          status: detail.status,
          remark: detail.remark,
          membership_role: detail.membership_role,
          department_item_id: detail.department_item_id,
          role_ids: detail.role_ids,
        })
        setDrawerTitle(t('users.edit'))
        setDrawerOpen(true)
      } catch (e) {
        showAppError(messageApi, t, e)
      }
    },
    [workspaceId, t, messageApi],
  )

  const handleSubmit = useCallback(
    async (
      values: SysUserCreateBody | Record<string, unknown>,
      context: { targetWorkspaceId: string },
    ) => {
      if (!workspaceId) return
      const { targetWorkspaceId } = context
      setSubmitting(true)
      try {
        if (drawerMode === 'create') {
          await createUser(targetWorkspaceId, values as SysUserCreateBody)
          if (targetWorkspaceId !== workspaceId) {
            messageApi.success(t('users.createSuccessOtherWorkspace'))
          } else {
            messageApi.success(t('users.createSuccess'))
          }
        } else if (editingId) {
          await patchUser(workspaceId, editingId, values as SysUserPatchBody)
          messageApi.success(t('users.updateSuccess'))
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
    [workspaceId, drawerMode, editingId, messageApi, t, reloadList],
  )

  const handleRemoveMembership = useCallback(
    async (row: SysUserListItem) => {
      if (!workspaceId) return
      try {
        await removeUserMembership(workspaceId, row.id)
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
      if (!workspaceId) return
      try {
        await deleteUserAccount(workspaceId, row.id)
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
        owner: t('users.membershipOwner'),
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
        render: (_v, row) => {
          const isSelf = userId != null && row.id === userId
          return isWorkspaceManager ? (
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
          ) : null
        },
      },
    ],
    [
      t,
      isWorkspaceManager,
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
            <Form.Item name="membership_role">
              <Select
                allowClear
                placeholder={t('users.membershipRole')}
                style={{ width: 120 }}
                options={[
                  { value: 'owner', label: t('users.membershipOwner') },
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
            <Form.Item>
              <Space>
                <Button type="primary" htmlType="submit">
                  {t('users.search')}
                </Button>
                <Button
                  onClick={() => {
                    filterForm.resetFields()
                    setFilters({})
                    setPage(1)
                  }}
                >
                  {t('users.reset')}
                </Button>
                {isWorkspaceManager ? (
                  <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
                    {t('users.add')}
                  </Button>
                ) : null}
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
            rowKey="id"
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
        pageWorkspaceId={workspaceId}
        initial={initialForm}
        onClose={() => setDrawerOpen(false)}
        onSubmit={handleSubmit}
      />
    </div>
  )
}
