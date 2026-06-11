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
import { useCallback, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { SysMenuNode } from '@/api/menus'
import {
  createRole,
  deleteRole,
  getRole,
  listRoleMenuTree,
  listRoles,
  patchRole,
  type SysRoleCreateBody,
  type SysRoleListItem,
  type SysRoleListParams,
} from '@/api/roles'
import { ApiError } from '@/api/client'
import { useAuth } from '@/app/AuthContext'
import { notifyMenuNavRefresh } from '@/app/menuNavRefresh'
import { showAppError, useAppMessage } from '@/app/useAppMessage'
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'
import { RoleFormDrawer, type RoleFormValues } from './RoleFormDrawer'
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

/** Workspace role management list with filters and permission drawer. */
export function RolesPage() {
  const { t } = useTranslation()
  const messageApi = useAppMessage()
  const { workspaceId, isWorkspaceManager } = useAuth()
  const [filterForm] = Form.useForm<FilterFormValues>()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [filters, setFilters] = useState<SysRoleListParams>({})
  const [refreshTick, setRefreshTick] = useState(0)
  const [forbidden, setForbidden] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerTitle, setDrawerTitle] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [initialForm, setInitialForm] = useState<RoleFormValues | null>(null)
  const [initialMenuIds, setInitialMenuIds] = useState<string[]>([])
  const [menuTree, setMenuTree] = useState<SysMenuNode[]>([])

  const listQuery = useQuery({
    queryKey: ['roles', workspaceId, page, pageSize, filters, refreshTick],
    queryFn: async () => {
      setForbidden(false)
      try {
        return await listRoles(workspaceId!, { ...filters, page, page_size: pageSize })
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

  const loadMenuTree = useCallback(async () => {
    if (!workspaceId) return []
    const tree = await listRoleMenuTree(workspaceId)
    setMenuTree(tree)
    return tree
  }, [workspaceId])

  const openCreate = useCallback(async () => {
    if (!workspaceId) return
    try {
      await loadMenuTree()
      setEditingId(null)
      setInitialForm({
        role_name: '',
        role_key: '',
        role_sort: 0,
        status: true,
        remark: null,
      })
      setInitialMenuIds([])
      setDrawerTitle(t('roles.add'))
      setDrawerOpen(true)
    } catch (e) {
      showAppError(messageApi, t, e)
    }
  }, [workspaceId, loadMenuTree, t, messageApi])

  const openEdit = useCallback(
    async (row: SysRoleListItem) => {
      if (!workspaceId) return
      try {
        await loadMenuTree()
        const detail = await getRole(workspaceId, row.id)
        setEditingId(row.id)
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
      }
    },
    [workspaceId, loadMenuTree, t, messageApi],
  )

  const handleSubmit = useCallback(
    async (body: SysRoleCreateBody) => {
      if (!workspaceId) return
      setSubmitting(true)
      try {
        if (editingId) {
          await patchRole(workspaceId, editingId, body)
          messageApi.success(t('roles.updateSuccess'))
        } else {
          await createRole(workspaceId, body)
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
    [workspaceId, editingId, messageApi, t, reloadList],
  )

  const handleDelete = useCallback(
    async (row: SysRoleListItem) => {
      if (!workspaceId) return
      try {
        await deleteRole(workspaceId, row.id)
        messageApi.success(t('roles.deleteSuccess'))
        reloadList()
      } catch (e) {
        showAppError(messageApi, t, e)
      }
    },
    [workspaceId, messageApi, t, reloadList],
  )

  const columns: ColumnsType<SysRoleListItem> = useMemo(
    () => [
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
        render: (_, row) =>
          isWorkspaceManager ? (
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
          ) : null,
      },
    ],
    [t, isWorkspaceManager, openEdit, handleDelete],
  )

  if (forbidden) {
    return <Result status="403" title={t('roles.forbiddenTitle')} subTitle={t('roles.forbiddenDesc')} />
  }

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
                    setPage(1)
                  }}
                >
                  {t('roles.reset')}
                </Button>
                {isWorkspaceManager ? (
                  <Button type="primary" icon={<PlusOutlined />} onClick={() => void openCreate()}>
                    {t('roles.add')}
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
            scroll={{ x: 980 }}
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
        menuTree={menuTree}
        initial={initialForm}
        initialMenuIds={initialMenuIds}
        onClose={() => setDrawerOpen(false)}
        onSubmit={handleSubmit}
      />
    </div>
  )
}
