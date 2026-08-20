import { DeleteOutlined } from '@ant-design/icons'
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
import { ApiError } from '@/api/client'
import {
  deleteTenantGrant,
  listTenantGrants,
  type SysUserGrant,
  type SysUserGrantListParams,
} from '@/api/grants'
import { useAuth } from '@/app/AuthContext'
import { useCanManageGrants } from '@/components/PermGuard'
import { showAppError, useAppMessage } from '@/app/useAppMessage'
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'
import './GrantsPage.css'

type FilterFormValues = {
  grant_type?: string
  scope_type?: string
  user_id?: string
}

/** Format ISO timestamp for table display. */
function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString(undefined, { hour12: false }) : '—'
}

/** Map filter form values to grant list API params. */
function toListParams(
  values: FilterFormValues,
  workspaceId: string | null,
  isWorkspaceAdmin: boolean,
): SysUserGrantListParams {
  const params: SysUserGrantListParams = {
    grant_type: values.grant_type || undefined,
    scope_type: values.scope_type || undefined,
    user_id: values.user_id?.trim() || undefined,
  }
  if (isWorkspaceAdmin && workspaceId) {
    params.workspace_id = workspaceId
  }
  return params
}

/** Tenant-scoped authorization grant list for grant managers. */
export function GrantsPage() {
  const { t } = useTranslation()
  const messageApi = useAppMessage()
  const { tenantId, workspaceId, isWorkspaceAdmin } = useAuth()
  const canManageGrants = useCanManageGrants()
  const [filterForm] = Form.useForm<FilterFormValues>()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [filters, setFilters] = useState<SysUserGrantListParams>({})
  const [refreshTick, setRefreshTick] = useState(0)
  const [forbidden, setForbidden] = useState(false)

  const listQuery = useQuery({
    queryKey: ['grants', tenantId, page, pageSize, filters, refreshTick],
    queryFn: async () => {
      setForbidden(false)
      try {
        return await listTenantGrants(tenantId!, { ...filters, page, page_size: pageSize })
      } catch (e) {
        if (e instanceof ApiError && e.code === 'auth.forbidden') {
          setForbidden(true)
          return { items: [], total: 0, page: 1, page_size: pageSize }
        }
        throw e
      }
    },
    enabled: Boolean(tenantId) && canManageGrants,
  })

  const reloadList = useCallback(() => {
    setRefreshTick((v) => v + 1)
  }, [])

  const handleDelete = useCallback(
    async (row: SysUserGrant) => {
      if (!tenantId) return
      try {
        await deleteTenantGrant(tenantId, row.id)
        messageApi.success(t('grants.deleteSuccess'))
        reloadList()
      } catch (e) {
        showAppError(messageApi, t, e)
      }
    },
    [tenantId, messageApi, t, reloadList],
  )

  const columns: ColumnsType<SysUserGrant> = useMemo(
    () => [
      {
        title: t('grants.grantType'),
        dataIndex: 'grant_type',
        width: 140,
      },
      {
        title: t('grants.userId'),
        dataIndex: 'user_id',
        width: 280,
        ellipsis: true,
      },
      {
        title: t('grants.scopeType'),
        dataIndex: 'scope_type',
        width: 120,
      },
      {
        title: t('grants.scopeId'),
        dataIndex: 'scope_id',
        width: 280,
        ellipsis: true,
        render: (value: string | null) => value ?? '—',
      },
      {
        title: t('grants.roleId'),
        dataIndex: 'role_id',
        width: 280,
        ellipsis: true,
        render: (value: string | null) => value ?? '—',
      },
      {
        title: t('grants.permissionId'),
        dataIndex: 'permission_id',
        width: 280,
        ellipsis: true,
        render: (value: string | null) => value ?? '—',
      },
      {
        title: t('grants.status'),
        dataIndex: 'status',
        width: 100,
        render: (value: boolean) => (
          <Tag color={value ? 'success' : 'default'}>
            {value ? t('grants.statusNormal') : t('grants.statusDisabled')}
          </Tag>
        ),
      },
      {
        title: t('grants.createAt'),
        dataIndex: 'create_at',
        width: 170,
        render: formatDateTime,
      },
      {
        title: t('grants.actions'),
        key: 'actions',
        width: 80,
        fixed: 'right',
        render: (_, row) => (
          <Tooltip title={t('grants.delete')}>
            <span>
              <Popconfirm
                title={t('grants.deleteTitle')}
                description={t('grants.deleteDesc')}
                onConfirm={() => void handleDelete(row)}
              >
                <Button
                  type="text"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  aria-label={t('grants.delete')}
                />
              </Popconfirm>
            </span>
          </Tooltip>
        ),
      },
    ],
    [t, handleDelete],
  )

  if (!tenantId) {
    return (
      <Result
        status="warning"
        title={t('grants.noTenantTitle')}
        subTitle={t('grants.noTenantDesc')}
      />
    )
  }

  if (!canManageGrants || forbidden) {
    return (
      <Result
        status="403"
        title={t('grants.forbiddenTitle')}
        subTitle={t('grants.forbiddenDesc')}
      />
    )
  }

  return (
    <div className="minerva-grants-page">
      <Card className="minerva-grants-page__card minerva-page-shell-card" bordered={false}>
        <div className="minerva-grants-page__header">
          <Form
            form={filterForm}
            layout="inline"
            onFinish={(values) => {
              setFilters(toListParams(values, workspaceId, isWorkspaceAdmin))
              setPage(1)
            }}
          >
            <Form.Item name="grant_type">
              <Select
                allowClear
                placeholder={t('grants.grantType')}
                style={{ width: 160 }}
                options={[
                  { value: 'role', label: t('grants.typeRole') },
                  { value: 'direct_permission', label: t('grants.typeDirectPermission') },
                ]}
              />
            </Form.Item>
            <Form.Item name="scope_type">
              <Select
                allowClear
                placeholder={t('grants.scopeType')}
                style={{ width: 140 }}
                options={[
                  { value: 'tenant', label: t('grants.scopeTenant') },
                  { value: 'workspace', label: t('grants.scopeWorkspace') },
                ]}
              />
            </Form.Item>
            <Form.Item name="user_id">
              <Input allowClear placeholder={t('grants.userIdPlaceholder')} style={{ width: 280 }} />
            </Form.Item>
            <Form.Item>
              <Space>
                <Button type="primary" htmlType="submit">
                  {t('grants.search')}
                </Button>
                <Button
                  onClick={() => {
                    filterForm.resetFields()
                    setFilters(
                      isWorkspaceAdmin && workspaceId
                        ? { workspace_id: workspaceId }
                        : {},
                    )
                    setPage(1)
                  }}
                >
                  {t('grants.reset')}
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
        <div className="minerva-grants-page__table-wrap">
          <Table<SysUserGrant>
            rowKey="id"
            size="small"
            loading={listQuery.isLoading}
            columns={columns}
            dataSource={listQuery.data?.items ?? []}
            scroll={{ x: 1800 }}
            pagination={{
              current: page,
              pageSize,
              total: listQuery.data?.total ?? 0,
              showSizeChanger: true,
              onChange: (nextPage, nextSize) => {
                setPage(nextPage)
                setPageSize(nextSize ?? DEFAULT_PAGE_SIZE)
              },
            }}
          />
        </div>
      </Card>
    </div>
  )
}
