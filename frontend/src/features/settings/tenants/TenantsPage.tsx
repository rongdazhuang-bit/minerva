import {
  ApartmentOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons'
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
import { useCallback, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  createTenant,
  deleteTenant,
  getTenant,
  listTenants,
  patchTenant,
  type SysTenantCreateBody,
  type SysTenantListItem,
  type SysTenantListParams,
} from '@/api/tenants'
import { putTenantAdmins, putTenantPermissions } from '@/api/tenantPermissions'
import { ApiError } from '@/api/client'
import { useAuth } from '@/app/AuthContext'
import { showAppError, useAppMessage } from '@/app/useAppMessage'
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'
import { TenantFormDrawer, type TenantCreatePermissions, type TenantFormValues } from './TenantFormDrawer'
import { TenantPermissionDrawer } from './TenantPermissionDrawer'
import { WorkspaceDrawer } from './WorkspaceDrawer'
import './TenantsPage.css'

type FilterFormValues = {
  name?: string
  status?: 'true' | 'false'
}

/** Format ISO timestamp for table display. */
function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString(undefined, { hour12: false }) : '—'
}

/** Map filter form values to list API params. */
function toListParams(values: FilterFormValues): SysTenantListParams {
  return {
    name: values.name?.trim() || undefined,
    status: values.status == null ? undefined : values.status === 'true',
  }
}

/** Platform super-admin tenant management list page. */
export function TenantsPage() {
  const { t } = useTranslation()
  const { isSuperAdmin } = useAuth()
  const messageApi = useAppMessage()
  const [filterForm] = Form.useForm<FilterFormValues>()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [filters, setFilters] = useState<SysTenantListParams>({})
  const [refreshTick, setRefreshTick] = useState(0)
  const [forbidden, setForbidden] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerTitle, setDrawerTitle] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [drawerMode, setDrawerMode] = useState<'create' | 'edit'>('create')
  const [initialForm, setInitialForm] = useState<TenantFormValues | null>(null)
  const [workspaceDrawerOpen, setWorkspaceDrawerOpen] = useState(false)
  const [workspaceTenant, setWorkspaceTenant] = useState<SysTenantListItem | null>(null)
  const [permissionOpen, setPermissionOpen] = useState(false)
  const [permissionTenant, setPermissionTenant] = useState<SysTenantListItem | null>(null)

  const listQuery = useQuery({
    queryKey: ['tenants', page, pageSize, filters, refreshTick],
    queryFn: async () => {
      setForbidden(false)
      try {
        return await listTenants({ ...filters, page, page_size: pageSize })
      } catch (e) {
        if (e instanceof ApiError && e.code === 'auth.forbidden') {
          setForbidden(true)
          return { items: [], total: 0, page: 1, page_size: pageSize }
        }
        throw e
      }
    },
    enabled: isSuperAdmin,
  })

  const reloadList = useCallback(() => {
    setRefreshTick((v) => v + 1)
  }, [])

  const openCreate = useCallback(() => {
    setEditingId(null)
    setDrawerMode('create')
    setInitialForm({
      name: '',
      slug: '',
      status: true,
      remark: null,
    })
    setDrawerTitle(t('tenants.addTenant'))
    setDrawerOpen(true)
  }, [t])

  const openEdit = useCallback(
    async (row: SysTenantListItem) => {
      try {
        const detail = await getTenant(row.id)
        setEditingId(row.id)
        setDrawerMode('edit')
        setInitialForm({
          name: detail.name,
          slug: detail.slug,
          status: detail.status,
          remark: detail.remark,
        })
        setDrawerTitle(t('tenants.editTenant'))
        setDrawerOpen(true)
      } catch (e) {
        showAppError(messageApi, t, e)
      }
    },
    [messageApi, t],
  )

  const openWorkspaces = useCallback((row: SysTenantListItem) => {
    setWorkspaceTenant(row)
    setWorkspaceDrawerOpen(true)
  }, [])

  const openPermissions = useCallback((row: SysTenantListItem) => {
    setPermissionTenant(row)
    setPermissionOpen(true)
  }, [])

  const handleSubmit = useCallback(
    async (body: SysTenantCreateBody, permissions: TenantCreatePermissions) => {
      setSubmitting(true)
      try {
        if (editingId) {
          await patchTenant(editingId, body)
          await putTenantPermissions(editingId, permissions.menu_ids)
          await putTenantAdmins(editingId, permissions.admin_user_ids)
          messageApi.success(t('tenants.updateSuccess'))
        } else {
          const created = await createTenant(body)
          await putTenantPermissions(created.id, permissions.menu_ids)
          messageApi.success(t('tenants.createSuccess'))
        }
        setDrawerOpen(false)
        reloadList()
      } catch (e) {
        showAppError(messageApi, t, e)
      } finally {
        setSubmitting(false)
      }
    },
    [editingId, messageApi, t, reloadList],
  )

  const handleDelete = useCallback(
    async (row: SysTenantListItem) => {
      try {
        await deleteTenant(row.id)
        messageApi.success(t('tenants.deleteSuccess'))
        reloadList()
      } catch (e) {
        showAppError(messageApi, t, e)
      }
    },
    [messageApi, t, reloadList],
  )

  const columns: ColumnsType<SysTenantListItem> = useMemo(
    () => [
      { title: t('tenants.tenantName'), dataIndex: 'name', width: 180 },
      { title: t('tenants.slug'), dataIndex: 'slug', width: 160 },
      {
        title: t('tenants.status'),
        dataIndex: 'status',
        width: 100,
        render: (status: boolean) => (
          <Tag color={status ? 'success' : 'default'}>
            {status ? t('tenants.statusNormal') : t('tenants.statusDisabled')}
          </Tag>
        ),
      },
      {
        title: t('tenants.createAt'),
        dataIndex: 'create_at',
        width: 170,
        render: formatDateTime,
      },
      {
        title: t('tenants.updateAt'),
        dataIndex: 'update_at',
        width: 170,
        render: formatDateTime,
      },
      {
        title: t('tenants.actions'),
        key: 'actions',
        width: 140,
        fixed: 'right',
        render: (_, row) => (
          <Space size={2}>
            <Tooltip title={t('tenants.edit')}>
              <Button
                type="text"
                size="small"
                icon={<EditOutlined />}
                onClick={() => void openEdit(row)}
                aria-label={t('tenants.edit')}
              />
            </Tooltip>
            <Tooltip title={t('tenants.workspaces')}>
              <Button
                type="text"
                size="small"
                icon={<ApartmentOutlined />}
                onClick={() => openWorkspaces(row)}
                aria-label={t('tenants.workspaces')}
              />
            </Tooltip>
            <Tooltip title={t('tenants.entitlements')}>
              <Button
                type="text"
                size="small"
                icon={<SafetyCertificateOutlined />}
                onClick={() => openPermissions(row)}
                aria-label={t('tenants.entitlements')}
              />
            </Tooltip>
            <Tooltip title={t('tenants.delete')}>
              <span>
                <Popconfirm
                  title={t('tenants.deleteTenantTitle', { name: row.name })}
                  description={t('tenants.deleteTenantDesc')}
                  onConfirm={() => void handleDelete(row)}
                >
                  <Button
                    type="text"
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                    aria-label={t('tenants.delete')}
                  />
                </Popconfirm>
              </span>
            </Tooltip>
          </Space>
        ),
      },
    ],
    [t, openWorkspaces, openPermissions, openEdit, handleDelete],
  )

  if (!isSuperAdmin || forbidden) {
    return (
      <Result
        status="403"
        title={t('tenants.forbiddenTitle')}
        subTitle={t('tenants.forbiddenDesc')}
      />
    )
  }

  return (
    <div className="minerva-tenants-page">
      <Card className="minerva-tenants-page__card" bordered={false}>
        <div className="minerva-tenants-page__header">
          <Form
            form={filterForm}
            layout="inline"
            onFinish={(values) => {
              setFilters(toListParams(values))
              setPage(1)
            }}
          >
            <Form.Item name="name">
              <Input allowClear placeholder={t('tenants.tenantNamePlaceholder')} style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="status">
              <Select
                allowClear
                placeholder={t('tenants.statusAll')}
                style={{ width: 120 }}
                options={[
                  { value: 'true', label: t('tenants.statusNormal') },
                  { value: 'false', label: t('tenants.statusDisabled') },
                ]}
              />
            </Form.Item>
            <Form.Item>
              <Space>
                <Button type="primary" htmlType="submit">
                  {t('tenants.search')}
                </Button>
                <Button
                  onClick={() => {
                    filterForm.resetFields()
                    setFilters({})
                    setPage(1)
                  }}
                >
                  {t('tenants.reset')}
                </Button>
                <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
                  {t('tenants.addTenant')}
                </Button>
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
        <div className="minerva-tenants-page__table-wrap">
          <Table<SysTenantListItem>
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
      <TenantFormDrawer
        open={drawerOpen}
        title={drawerTitle}
        mode={drawerMode}
        tenantId={editingId}
        submitting={submitting}
        initial={initialForm}
        onClose={() => setDrawerOpen(false)}
        onSubmit={handleSubmit}
      />
      <WorkspaceDrawer
        open={workspaceDrawerOpen}
        tenant={workspaceTenant}
        onClose={() => {
          setWorkspaceDrawerOpen(false)
          setWorkspaceTenant(null)
        }}
      />
      <TenantPermissionDrawer
        open={permissionOpen}
        tenant={permissionTenant}
        onClose={() => {
          setPermissionOpen(false)
          setPermissionTenant(null)
        }}
        onSaved={reloadList}
      />
    </div>
  )
}
