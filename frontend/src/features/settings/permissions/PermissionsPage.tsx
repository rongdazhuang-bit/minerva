import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Result,
  Space,
  Table,
  Tag,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  listPermissions,
  type SysPermission,
  type SysPermissionListParams,
} from '@/api/permissions'
import { ApiError } from '@/api/client'
import { useAuth } from '@/app/AuthContext'
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'
import './PermissionsPage.css'

type FilterFormValues = {
  perm_code?: string
  perm_type?: string
}

/** Format ISO timestamp for table display. */
function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString(undefined, { hour12: false }) : '—'
}

/** Map filter form values to list API params. */
function toListParams(values: FilterFormValues): SysPermissionListParams {
  return {
    perm_code: values.perm_code?.trim() || undefined,
    perm_type: values.perm_type?.trim() || undefined,
  }
}

/** Super-admin read-only catalog of global permission codes. */
export function PermissionsPage() {
  const { t } = useTranslation()
  const { isSuperAdmin } = useAuth()
  const [filterForm] = Form.useForm<FilterFormValues>()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [filters, setFilters] = useState<SysPermissionListParams>({})
  const [forbidden, setForbidden] = useState(false)

  const listQuery = useQuery({
    queryKey: ['permissions', page, pageSize, filters],
    queryFn: async () => {
      setForbidden(false)
      try {
        return await listPermissions({ ...filters, page, page_size: pageSize })
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

  const columns: ColumnsType<SysPermission> = useMemo(
    () => [
      {
        title: t('permissions.permCode'),
        dataIndex: 'perm_code',
        width: 220,
        ellipsis: true,
      },
      {
        title: t('permissions.permName'),
        dataIndex: 'perm_name',
        width: 180,
        ellipsis: true,
      },
      {
        title: t('permissions.permType'),
        dataIndex: 'perm_type',
        width: 120,
      },
      {
        title: t('permissions.resourcePattern'),
        dataIndex: 'resource_pattern',
        width: 200,
        ellipsis: true,
        render: (value: string | null) => value ?? '—',
      },
      {
        title: t('permissions.status'),
        dataIndex: 'status',
        width: 100,
        render: (value: boolean) => (
          <Tag color={value ? 'success' : 'default'}>
            {value ? t('permissions.statusNormal') : t('permissions.statusDisabled')}
          </Tag>
        ),
      },
      {
        title: t('permissions.remark'),
        dataIndex: 'remark',
        ellipsis: true,
        render: (value: string | null) => value ?? '—',
      },
      {
        title: t('permissions.createAt'),
        dataIndex: 'create_at',
        width: 170,
        render: formatDateTime,
      },
    ],
    [t],
  )

  if (!isSuperAdmin || forbidden) {
    return (
      <Result
        status="403"
        title={t('permissions.forbiddenTitle')}
        subTitle={t('permissions.forbiddenDesc')}
      />
    )
  }

  return (
    <div className="minerva-permissions-page">
      <Card className="minerva-permissions-page__card minerva-page-shell-card" bordered={false}>
        <div className="minerva-permissions-page__header">
          <Form
            form={filterForm}
            layout="inline"
            onFinish={(values) => {
              setFilters(toListParams(values))
              setPage(1)
            }}
          >
            <Form.Item name="perm_code">
              <Input allowClear placeholder={t('permissions.permCodePlaceholder')} style={{ width: 200 }} />
            </Form.Item>
            <Form.Item name="perm_type">
              <Input allowClear placeholder={t('permissions.permTypePlaceholder')} style={{ width: 160 }} />
            </Form.Item>
            <Form.Item>
              <Space>
                <Button type="primary" htmlType="submit">
                  {t('permissions.search')}
                </Button>
                <Button
                  onClick={() => {
                    filterForm.resetFields()
                    setFilters({})
                    setPage(1)
                  }}
                >
                  {t('permissions.reset')}
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
        <div className="minerva-permissions-page__table-wrap">
          <Table<SysPermission>
            rowKey="id"
            size="small"
            loading={listQuery.isLoading}
            columns={columns}
            dataSource={listQuery.data?.items ?? []}
            scroll={{ x: 1100 }}
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
