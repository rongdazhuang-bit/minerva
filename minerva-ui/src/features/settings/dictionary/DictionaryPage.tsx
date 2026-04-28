import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons'
import {
  Button,
  Card,
  Drawer,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Space,
  Table,
  TreeSelect,
  Typography,
  message,
} from 'antd'
import type { TreeSelectProps } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError } from '@/api/client'
import { useQueryClient } from '@tanstack/react-query'
import {
  createDict,
  createDictItem,
  deleteDict,
  deleteDictItem,
  listDictItems,
  listDicts,
  patchDict,
  patchDictItem,
  type SysDictItem,
  type SysDictListItem,
} from '@/api/dicts'
import { useAuth } from '@/app/AuthContext'
import { dictQueryKeys } from '@/constants/dictQueryKeys'
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'
import './DictionaryPage.css'

const { Paragraph, Text } = Typography

type DictFormValues = {
  dict_code: string
  dict_name?: string
  dict_sort?: number | null
}

type ItemFormValues = {
  code: string
  name: string
  item_sort?: number | null
  parent_uuid?: string | null
}

type ItemRow = SysDictItem & { children?: ItemRow[] }

function sortItemNodes(nodes: ItemRow[]) {
  nodes.sort(
    (a, b) =>
      (b.item_sort ?? 0) - (a.item_sort ?? 0) || a.code.localeCompare(b.code),
  )
  for (const n of nodes) {
    if (n.children?.length) sortItemNodes(n.children)
  }
}

function buildItemTree(flat: SysDictItem[]): ItemRow[] {
  const byId = new Map<string, ItemRow>()
  for (const r of flat) {
    byId.set(r.id, { ...r, children: [] })
  }
  const roots: ItemRow[] = []
  for (const r of flat) {
    const node = byId.get(r.id)!
    if (r.parent_uuid && byId.has(r.parent_uuid)) {
      byId.get(r.parent_uuid)!.children!.push(node)
    } else {
      roots.push(node)
    }
  }
  sortItemNodes(roots)
  const prune = (nodes: ItemRow[]) => {
    for (const n of nodes) {
      if (n.children?.length) prune(n.children)
      else delete n.children
    }
  }
  prune(roots)
  return roots
}

function descendantIds(flat: SysDictItem[], itemId: string): Set<string> {
  const byParent = new Map<string | null, string[]>()
  for (const r of flat) {
    const p = r.parent_uuid ?? null
    if (!byParent.has(p)) byParent.set(p, [])
    byParent.get(p)!.push(r.id)
  }
  const out = new Set<string>()
  const stack = [...(byParent.get(itemId) ?? [])]
  while (stack.length) {
    const id = stack.pop()!
    if (out.has(id)) continue
    out.add(id)
    stack.push(...(byParent.get(id) ?? []))
  }
  return out
}

function showErr(t: (k: string) => string, e: unknown) {
  if (e instanceof ApiError) {
    void message.error(e.message)
    return
  }
  void message.error(t('common.error'))
}

function buildParentTreeData(
  nodes: ItemRow[],
  forbidden: Set<string>,
): NonNullable<TreeSelectProps['treeData']> {
  const out: NonNullable<TreeSelectProps['treeData']> = []
  for (const n of nodes) {
    if (forbidden.has(n.id)) continue
    const rawChildren = n.children
    const children =
      rawChildren && rawChildren.length > 0
        ? buildParentTreeData(rawChildren, forbidden)
        : undefined
    out.push({
      title: `${n.code} — ${n.name}`,
      value: n.id,
      key: n.id,
      ...(children && children.length > 0 ? { children } : {}),
    })
  }
  return out
}

function renderCodeCopyable(code: string, t: (k: string) => string) {
  const v = code.trim()
  if (!v) return '—'
  return (
    <Typography.Text
      copyable={{
        onCopy: () => void message.success(t('common.copied')),
      }}
      ellipsis={{ tooltip: v }}
      style={{ maxWidth: '100%' }}
    >
      {v}
    </Typography.Text>
  )
}

export function DictionaryPage() {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const queryClient = useQueryClient()
  const invalidateWorkspaceDictCache = useCallback(() => {
    if (!workspaceId) return
    void queryClient.invalidateQueries({ queryKey: dictQueryKeys.all(workspaceId) })
  }, [queryClient, workspaceId])
  const [dictForm] = Form.useForm<DictFormValues>()
  const [itemForm] = Form.useForm<ItemFormValues>()

  const [loading, setLoading] = useState(false)
  const [dictListRev, setDictListRev] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [total, setTotal] = useState(0)
  const [dicts, setDicts] = useState<SysDictListItem[]>([])
  const [dictModalOpen, setDictModalOpen] = useState(false)
  const [dictSubmitting, setDictSubmitting] = useState(false)
  const [editingDictId, setEditingDictId] = useState<string | null>(null)

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [activeDict, setActiveDict] = useState<SysDictListItem | null>(null)
  const [itemsFlat, setItemsFlat] = useState<SysDictItem[]>([])
  const [itemsLoading, setItemsLoading] = useState(false)
  const [itemModalOpen, setItemModalOpen] = useState(false)
  const [itemSubmitting, setItemSubmitting] = useState(false)
  const [editingItemId, setEditingItemId] = useState<string | null>(null)

  useEffect(() => {
    if (!workspaceId) return
    let cancelled = false
    setLoading(true)
    void (async () => {
      try {
        const data = await listDicts(workspaceId, { page, page_size: pageSize })
        if (cancelled) return
        const maxPage = Math.max(1, Math.ceil(data.total / pageSize) || 1)
        if (page > maxPage) {
          setPage(maxPage)
          return
        }
        setDicts(data.items)
        setTotal(data.total)
      } catch (e) {
        if (!cancelled) showErr(t, e)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [workspaceId, page, pageSize, dictListRev, t])

  const loadItems = useCallback(async () => {
    if (!workspaceId || !activeDict) return
    setItemsLoading(true)
    try {
      const rows = await listDictItems(workspaceId, activeDict.id)
      setItemsFlat(rows)
    } catch (e) {
      showErr(t, e)
    } finally {
      setItemsLoading(false)
    }
  }, [activeDict, t, workspaceId])

  useEffect(() => {
    if (drawerOpen && activeDict) void loadItems()
  }, [drawerOpen, activeDict, loadItems])

  const itemTree = useMemo(() => buildItemTree(itemsFlat), [itemsFlat])

  const parentTreeData = useMemo(() => {
    const forbidden = editingItemId
      ? new Set([editingItemId, ...descendantIds(itemsFlat, editingItemId)])
      : new Set<string>()
    return buildParentTreeData(itemTree, forbidden)
  }, [editingItemId, itemTree, itemsFlat])

  const openCreateDict = () => {
    setEditingDictId(null)
    dictForm.resetFields()
    dictForm.setFieldsValue({ dict_sort: 0 })
    setDictModalOpen(true)
  }

  const openEditDict = (row: SysDictListItem) => {
    setEditingDictId(row.id)
    dictForm.setFieldsValue({
      dict_code: row.dict_code,
      dict_name: row.dict_name ?? '',
      dict_sort: row.dict_sort ?? 0,
    })
    setDictModalOpen(true)
  }

  const onDictSubmit = async (values: DictFormValues) => {
    if (!workspaceId) return
    setDictSubmitting(true)
    try {
      const payload = {
        dict_code: values.dict_code.trim(),
        dict_name: values.dict_name?.trim() || null,
        dict_sort: values.dict_sort ?? 0,
      }
      let saved: SysDictListItem
      if (editingDictId) {
        saved = await patchDict(workspaceId, editingDictId, payload)
        void message.success(t('settings.dictUpdated'))
      } else {
        saved = await createDict(workspaceId, payload)
        void message.success(t('settings.dictCreated'))
      }
      setDictModalOpen(false)
      if (editingDictId && activeDict?.id === editingDictId) {
        setActiveDict(saved)
      }
      if (!editingDictId) {
        setPage(1)
      }
      setDictListRev((n) => n + 1)
      invalidateWorkspaceDictCache()
    } catch (e) {
      showErr(t, e)
    } finally {
      setDictSubmitting(false)
    }
  }

  const handleDeleteDict = async (id: string) => {
    if (!workspaceId) return
    try {
      await deleteDict(workspaceId, id)
      void message.success(t('settings.dictDeleted'))
      if (activeDict?.id === id) {
        setDrawerOpen(false)
        setActiveDict(null)
      }
      setDictListRev((n) => n + 1)
      invalidateWorkspaceDictCache()
    } catch (e) {
      showErr(t, e)
    }
  }

  const openItemsDrawer = (row: SysDictListItem) => {
    setActiveDict(row)
    setDrawerOpen(true)
  }

  const openCreateItem = () => {
    setEditingItemId(null)
    itemForm.resetFields()
    itemForm.setFieldsValue({ item_sort: 0 })
    setItemModalOpen(true)
  }

  const openEditItem = (row: SysDictItem) => {
    setEditingItemId(row.id)
    itemForm.setFieldsValue({
      code: row.code,
      name: row.name,
      item_sort: row.item_sort ?? 0,
      parent_uuid: row.parent_uuid ?? undefined,
    })
    setItemModalOpen(true)
  }

  const onItemSubmit = async (values: ItemFormValues) => {
    if (!workspaceId || !activeDict) return
    setItemSubmitting(true)
    try {
      const parent = values.parent_uuid != null ? values.parent_uuid : null
      const payload = {
        code: values.code.trim(),
        name: values.name.trim(),
        item_sort: values.item_sort ?? 0,
        parent_uuid: parent,
      }
      if (editingItemId) {
        await patchDictItem(workspaceId, activeDict.id, editingItemId, payload)
        void message.success(t('settings.dictItemUpdated'))
      } else {
        await createDictItem(workspaceId, activeDict.id, payload)
        void message.success(t('settings.dictItemCreated'))
      }
      setItemModalOpen(false)
      await loadItems()
      invalidateWorkspaceDictCache()
    } catch (e) {
      showErr(t, e)
    } finally {
      setItemSubmitting(false)
    }
  }

  const handleDeleteItem = async (itemId: string) => {
    if (!workspaceId || !activeDict) return
    try {
      await deleteDictItem(workspaceId, activeDict.id, itemId)
      void message.success(t('settings.dictItemDeleted'))
      await loadItems()
      invalidateWorkspaceDictCache()
    } catch (e) {
      showErr(t, e)
    }
  }

  const dictColumns: ColumnsType<SysDictListItem> = [
    {
      title: t('settings.dictCode'),
      dataIndex: 'dict_code',
      key: 'dict_code',
      width: 200,
      ellipsis: true,
      render: (v: string) => renderCodeCopyable(v, t),
    },
    {
      title: t('settings.dictName'),
      dataIndex: 'dict_name',
      key: 'dict_name',
      width: 180,
      ellipsis: true,
      render: (v: string | null) => v ?? '—',
    },
    {
      title: t('settings.dictSort'),
      dataIndex: 'dict_sort',
      key: 'dict_sort',
      width: 90,
    },
    {
      title: t('settings.dictCreatedAt'),
      dataIndex: 'create_at',
      key: 'create_at',
      width: 200,
      ellipsis: true,
      render: (v: string | null) =>
        v ? new Date(v).toLocaleString(undefined, { hour12: false }) : '—',
    },
    {
      title: t('settings.dictActions'),
      key: 'actions',
      width: 200,
      render: (_, row) => (
        <Space>
          <Button
            type="text"
            icon={<UnorderedListOutlined />}
            onClick={() => openItemsDrawer(row)}
            aria-label={t('settings.dictItems')}
          />
          <Button
            type="text"
            icon={<EditOutlined />}
            onClick={() => openEditDict(row)}
            aria-label={t('settings.dictEdit')}
          />
          <Popconfirm
            title={t('settings.dictDeleteConfirm')}
            onConfirm={() => void handleDeleteDict(row.id)}
          >
            <Button
              type="text"
              danger
              icon={<DeleteOutlined />}
              aria-label={t('settings.dictDelete')}
            />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const itemColumns: ColumnsType<ItemRow> = [
    {
      title: t('settings.dictItemCode'),
      dataIndex: 'code',
      key: 'code',
      width: 200,
      ellipsis: true,
      render: (v: string) => renderCodeCopyable(v, t),
    },
    {
      title: t('settings.dictItemName'),
      dataIndex: 'name',
      key: 'name',
      width: 160,
      ellipsis: true,
    },
    {
      title: t('settings.dictItemSort'),
      dataIndex: 'item_sort',
      key: 'item_sort',
      width: 90,
    },
    {
      title: t('settings.dictActions'),
      key: 'actions',
      width: 120,
      render: (_, row) => (
        <Space>
          <Button
            type="text"
            icon={<EditOutlined />}
            onClick={() => openEditItem(row)}
            aria-label={t('settings.dictItemEdit')}
          />
          <Popconfirm
            title={t('settings.dictItemDeleteConfirm')}
            onConfirm={() => void handleDeleteItem(row.id)}
          >
            <Button
              type="text"
              danger
              icon={<DeleteOutlined />}
              aria-label={t('settings.dictItemDelete')}
            />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  if (!workspaceId) {
    return (
      <div className="minerva-dict-settings">
        <Paragraph>{t('settings.ocrNoWorkspace')}</Paragraph>
      </div>
    )
  }

  return (
    <div className="minerva-dict-settings">
      <Card size="small" variant="borderless" className="minerva-dict-settings__card">
        <Space className="minerva-dict-settings__toolbar">
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreateDict}>
            {t('settings.dictAdd')}
          </Button>
        </Space>

        <div className="minerva-dict-settings__table-wrap">
          <Table<SysDictListItem>
            rowKey="id"
            loading={loading}
            columns={dictColumns}
            dataSource={dicts}
            pagination={{
              current: page,
              pageSize,
              total,
              showSizeChanger: true,
              pageSizeOptions: [10, 20, 50, 100],
              onChange: (p, ps) => {
                setPage(p)
                setPageSize(ps)
              },
            }}
            size="middle"
            className="minerva-dict-settings__table"
            scroll={{ x: true, y: 'calc(100dvh - 360px)' }}
            sticky
          />
        </div>
      </Card>

      <Drawer
        width={640}
        placement="right"
        open={dictModalOpen}
        title={editingDictId ? t('settings.dictEdit') : t('settings.dictAdd')}
        onClose={() => setDictModalOpen(false)}
        destroyOnClose
        classNames={{ body: 'minerva-scrollbar-styled' }}
        extra={
          <Space>
            <Button onClick={() => setDictModalOpen(false)}>{t('common.cancel')}</Button>
            <Button type="primary" loading={dictSubmitting} onClick={() => void dictForm.submit()}>
              {t('common.save')}
            </Button>
          </Space>
        }
      >
        <Form form={dictForm} layout="vertical" onFinish={(v) => void onDictSubmit(v)}>
          <Form.Item
            name="dict_code"
            label={t('settings.dictCode')}
            extra={editingDictId ? <Text type="secondary">{t('settings.dictCodeEditHint')}</Text> : null}
            rules={[{ required: true, message: t('settings.dictCodeRequired') }]}
          >
            <Input allowClear maxLength={64} />
          </Form.Item>
          <Form.Item name="dict_name" label={t('settings.dictName')}>
            <Input allowClear maxLength={128} />
          </Form.Item>
          <Form.Item name="dict_sort" label={t('settings.dictSort')}>
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Drawer>

      <Drawer
        title={
          activeDict ? (
            <span>
              {activeDict.dict_name ?? activeDict.dict_code}
              {' ('}
              <Typography.Text
                copyable={{
                  onCopy: () => void message.success(t('common.copied')),
                }}
                style={{ wordBreak: 'break-all' }}
              >
                {activeDict.dict_code}
              </Typography.Text>
              {')'}
            </span>
          ) : (
            t('settings.dictItems')
          )
        }
        width={720}
        placement="right"
        open={drawerOpen}
        onClose={() => {
          setDrawerOpen(false)
          setActiveDict(null)
          setItemsFlat([])
        }}
        classNames={{ body: 'minerva-scrollbar-styled' }}
        styles={{ body: { display: 'flex', flexDirection: 'column', minHeight: 0 } }}
      >
        <div className="minerva-dict-settings__drawer-body">
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreateItem}>
            {t('settings.dictItemAdd')}
          </Button>
          <div className="minerva-dict-settings__drawer-table-wrap">
            <Table<ItemRow>
              rowKey="id"
              loading={itemsLoading}
              columns={itemColumns}
              dataSource={itemTree}
              pagination={false}
              size="small"
              className="minerva-dict-settings__drawer-table"
              scroll={{ x: true, y: 'calc(100dvh - 260px)' }}
              expandable={{ defaultExpandAllRows: true }}
            />
          </div>
        </div>
      </Drawer>

      <Drawer
        width={640}
        placement="right"
        open={itemModalOpen}
        title={editingItemId ? t('settings.dictItemEdit') : t('settings.dictItemAdd')}
        onClose={() => setItemModalOpen(false)}
        destroyOnClose
        classNames={{ body: 'minerva-scrollbar-styled' }}
        extra={
          <Space>
            <Button onClick={() => setItemModalOpen(false)}>{t('common.cancel')}</Button>
            <Button type="primary" loading={itemSubmitting} onClick={() => void itemForm.submit()}>
              {t('common.save')}
            </Button>
          </Space>
        }
      >
        <Form form={itemForm} layout="vertical" onFinish={(v) => void onItemSubmit(v)}>
          <Form.Item
            name="code"
            label={t('settings.dictItemCode')}
            rules={[{ required: true, message: t('settings.dictItemCodeRequired') }]}
          >
            <Input allowClear maxLength={64} />
          </Form.Item>
          <Form.Item
            name="name"
            label={t('settings.dictItemName')}
            rules={[{ required: true, message: t('settings.dictItemNameRequired') }]}
          >
            <Input allowClear maxLength={64} />
          </Form.Item>
          <Form.Item name="item_sort" label={t('settings.dictItemSort')}>
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="parent_uuid" label={t('settings.dictItemParent')}>
            <TreeSelect
              allowClear
              showSearch
              treeDefaultExpandAll
              placeholder={t('settings.dictItemParentPlaceholder')}
              treeData={parentTreeData}
              treeNodeFilterProp="title"
              style={{ width: '100%' }}
            />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  )
}
