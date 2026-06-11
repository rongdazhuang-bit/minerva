import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
} from '@ant-design/icons'
import {
  Button,
  Drawer,
  Form,
  Input,
  Popconfirm,
  Radio,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  createWorkspace,
  deleteWorkspace,
  getWorkspace,
  listWorkspaces,
  patchWorkspace,
  type SysTenantListItem,
  type SysWorkspaceCreateBody,
  type SysWorkspaceListItem,
  type SysWorkspaceListParams,
} from '@/api/tenants'
import { showAppError, useAppMessage } from '@/app/useAppMessage'
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'

/** Form values for create/edit workspace drawer. */
type WorkspaceFormValues = {
  name: string
  slug: string
  status?: boolean
  remark?: string | null
}

type Props = {
  open: boolean
  tenant: SysTenantListItem | null
  onClose: () => void
}

/** Format ISO timestamp for table display. */
function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString(undefined, { hour12: false }) : '—'
}

/** Drawer listing and managing workspaces for one tenant. */
export function WorkspaceDrawer({ open, tenant, onClose }: Props) {
  const { t } = useTranslation()
  const messageApi = useAppMessage()
  const [filterForm] = Form.useForm<{ name?: string; status?: 'true' | 'false' }>()
  const [form] = Form.useForm<WorkspaceFormValues>()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [filters, setFilters] = useState<SysWorkspaceListParams>({})
  const [loading, setLoading] = useState(false)
  const [items, setItems] = useState<SysWorkspaceListItem[]>([])
  const [total, setTotal] = useState(0)
  const [formOpen, setFormOpen] = useState(false)
  const [formTitle, setFormTitle] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!tenant) return
    setLoading(true)
    try {
      const data = await listWorkspaces(tenant.id, {
        ...filters,
        page,
        page_size: pageSize,
      })
      setItems(data.items)
      setTotal(data.total)
    } catch (e) {
      showAppError(messageApi, t, e)
    } finally {
      setLoading(false)
    }
  }, [tenant, filters, page, pageSize, messageApi, t])

  useEffect(() => {
    if (!open || !tenant) return
    void load()
  }, [open, tenant, load])

  const openCreate = useCallback(() => {
    setEditingId(null)
    form.setFieldsValue({
      name: '',
      slug: '',
      status: true,
      remark: null,
    })
    setFormTitle(t('tenants.addWorkspace'))
    setFormOpen(true)
  }, [form, t])

  const openEdit = useCallback(
    async (row: SysWorkspaceListItem) => {
      if (!tenant) return
      try {
        const detail = await getWorkspace(tenant.id, row.id)
        setEditingId(row.id)
        form.setFieldsValue({
          name: detail.name,
          slug: detail.slug,
          status: detail.status,
          remark: detail.remark,
        })
        setFormTitle(t('tenants.editWorkspace'))
        setFormOpen(true)
      } catch (e) {
        showAppError(messageApi, t, e)
      }
    },
    [tenant, form, t, messageApi],
  )

  const handleSubmit = useCallback(
    async (values: SysWorkspaceCreateBody) => {
      if (!tenant) return
      setSubmitting(true)
      try {
        if (editingId) {
          await patchWorkspace(tenant.id, editingId, values)
          messageApi.success(t('tenants.workspaceUpdateSuccess'))
        } else {
          await createWorkspace(tenant.id, values)
          messageApi.success(t('tenants.workspaceCreateSuccess'))
        }
        setFormOpen(false)
        void load()
      } catch (e) {
        showAppError(messageApi, t, e)
      } finally {
        setSubmitting(false)
      }
    },
    [tenant, editingId, messageApi, t, load],
  )

  const handleDelete = useCallback(
    async (row: SysWorkspaceListItem) => {
      if (!tenant) return
      try {
        await deleteWorkspace(tenant.id, row.id)
        messageApi.success(t('tenants.workspaceDeleteSuccess'))
        void load()
      } catch (e) {
        showAppError(messageApi, t, e)
      }
    },
    [tenant, messageApi, t, load],
  )

  const columns: ColumnsType<SysWorkspaceListItem> = useMemo(
    () => [
      { title: t('tenants.name'), dataIndex: 'name', width: 160 },
      { title: t('tenants.slug'), dataIndex: 'slug', width: 140 },
      {
        title: t('tenants.status'),
        dataIndex: 'status',
        width: 90,
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
        title: t('tenants.actions'),
        key: 'actions',
        width: 88,
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
            <Tooltip title={t('tenants.delete')}>
              <span>
                <Popconfirm
                  title={t('tenants.deleteWorkspaceTitle', { name: row.name })}
                  description={t('tenants.deleteWorkspaceDesc')}
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
    [t, openEdit, handleDelete],
  )

  return (
    <>
      <Drawer
        title={tenant ? `${tenant.name} — ${t('tenants.workspaces')}` : t('tenants.workspaces')}
        width={720}
        open={open}
        onClose={onClose}
        destroyOnClose
        classNames={{ body: 'minerva-scrollbar-styled' }}
        styles={{ body: { display: 'flex', flexDirection: 'column', minHeight: 0 } }}
      >
        <div className="minerva-tenants-workspace-drawer__body">
          <div className="minerva-tenants-workspace-drawer__toolbar">
            <Form
              className="minerva-tenants-workspace-drawer__filter"
              form={filterForm}
              layout="inline"
              onFinish={(values) => {
                setFilters({
                  name: values.name?.trim() || undefined,
                  status:
                    values.status == null ? undefined : values.status === 'true',
                })
                setPage(1)
              }}
            >
              <Form.Item name="name">
                <Input allowClear placeholder={t('tenants.workspaceNamePlaceholder')} style={{ width: 160 }} />
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
                </Space>
              </Form.Item>
            </Form>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              {t('tenants.addWorkspace')}
            </Button>
          </div>
          <div className="minerva-tenants-workspace-drawer__table-wrap">
            <Table<SysWorkspaceListItem>
              className="minerva-card-table-scroll-ocr"
              rowKey="id"
              loading={loading}
              columns={columns}
              dataSource={items}
              size="small"
              scroll={{ x: 720, y: 'calc(100dvh - 280px)' }}
              sticky
              pagination={{
                current: page,
                pageSize,
                total,
                showSizeChanger: true,
                onChange: (p, ps) => {
                  setPage(p)
                  setPageSize(ps)
                },
              }}
            />
          </div>
        </div>
      </Drawer>
      <Drawer
        title={formTitle}
        width={480}
        open={formOpen}
        onClose={() => setFormOpen(false)}
        destroyOnClose
        footer={null}
        classNames={{ body: 'minerva-scrollbar-styled' }}
        extra={
          <Space>
            <Button onClick={() => setFormOpen(false)} disabled={submitting}>
              {t('tenants.cancel')}
            </Button>
            <Button type="primary" loading={submitting} onClick={() => void form.submit()}>
              {t('tenants.save')}
            </Button>
          </Space>
        }
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          <Form.Item
            name="name"
            label={t('tenants.workspaceName')}
            rules={[{ required: true, message: t('tenants.workspaceNameRequired') }]}
          >
            <Input allowClear placeholder={t('tenants.workspaceNamePlaceholder')} />
          </Form.Item>
          <Form.Item
            name="slug"
            label={t('tenants.slug')}
            rules={[{ required: true, message: t('tenants.slugRequired') }]}
          >
            <Input allowClear placeholder={t('tenants.slugPlaceholder')} />
          </Form.Item>
          <Form.Item name="status" label={t('tenants.status')} rules={[{ required: true }]}>
            <Radio.Group>
              <Radio value={true}>{t('tenants.statusNormal')}</Radio>
              <Radio value={false}>{t('tenants.statusDisabled')}</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="remark" label={t('tenants.remark')}>
            <Input.TextArea allowClear rows={3} placeholder={t('tenants.remarkPlaceholder')} />
          </Form.Item>
        </Form>
      </Drawer>
    </>
  )
}
