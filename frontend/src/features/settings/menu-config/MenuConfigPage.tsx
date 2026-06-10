import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  SwapOutlined,
} from '@ant-design/icons'
import {
  Button,
  Card,
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
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  createMenu,
  deleteMenu,
  listMenus,
  patchMenu,
  type SysMenuCreateBody,
  type SysMenuNode,
} from '@/api/menus'
import { ApiError } from '@/api/client'
import { notifyMenuNavRefresh } from '@/app/menuNavRefresh'
import { showAppError, useAppMessage } from '@/app/useAppMessage'
import { MenuFormDrawer, type MenuFormValues } from './MenuFormDrawer'
import { resolveMenuIcon } from './menuIconMap'
import './MenuConfigPage.css'

/** 表体横向滚动最小宽度（列宽之和，含固定列）。 */
const MENU_CONFIG_TABLE_SCROLL_X = 1080

/** 表头与边框占用高度，从容器实测高度中扣除得到表体 scroll.y。 */
const MENU_CONFIG_TABLE_SCROLL_GUTTER_PX = 48

type MenuRow = SysMenuNode & { children?: MenuRow[] }

function countDescendants(node: SysMenuNode): number {
  let n = 0
  const walk = (items: SysMenuNode[]) => {
    for (const c of items) {
      n += 1
      if (c.children?.length) walk(c.children)
    }
  }
  if (node.children?.length) walk(node.children)
  return n
}

function nodeToFormValues(node: SysMenuNode): MenuFormValues {
  return {
    parent_id: node.parent_id,
    menu_name: node.menu_name,
    menu_type: node.menu_type,
    i18n_key: node.i18n_key,
    menu_key: node.menu_key,
    order_num: node.order_num,
    path: node.path,
    perms: node.perms,
    icon: node.icon,
    visible: node.visible,
    status: node.status,
    is_external: node.is_external,
    remark: node.remark,
  }
}

export function MenuConfigPage() {
  const { t } = useTranslation()
  const messageApi = useAppMessage()
  const tableWrapRef = useRef<HTMLDivElement | null>(null)
  const [tableBodyScrollY, setTableBodyScrollY] = useState(320)
  const [loading, setLoading] = useState(false)
  const [forbidden, setForbidden] = useState(false)
  const [tree, setTree] = useState<MenuRow[]>([])
  const [rev, setRev] = useState(0)
  const [nameFilter, setNameFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState<boolean | undefined>(undefined)
  const [expandedKeys, setExpandedKeys] = useState<string[]>([])
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [defaultParentId, setDefaultParentId] = useState<string | null>(null)
  const [initialForm, setInitialForm] = useState<MenuFormValues | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setForbidden(false)
    try {
      const data = await listMenus({
        menu_name: nameFilter || undefined,
        status: statusFilter,
      })
      setTree(data as MenuRow[])
    } catch (e) {
      if (e instanceof ApiError && e.code === 'auth.forbidden') {
        setForbidden(true)
        setTree([])
      } else {
        showAppError(messageApi, t, e)
      }
    } finally {
      setLoading(false)
    }
  }, [messageApi, nameFilter, statusFilter, t])

  useEffect(() => {
    void load()
  }, [load, rev])

  useLayoutEffect(() => {
    const wrap = tableWrapRef.current
    if (wrap == null) return
    const measure = () => {
      const h = wrap.getBoundingClientRect().height
      setTableBodyScrollY(Math.max(120, Math.floor(h - MENU_CONFIG_TABLE_SCROLL_GUTTER_PX)))
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(wrap)
    return () => {
      ro.disconnect()
    }
  }, [tree.length, loading, forbidden])

  const allKeys = useMemo(() => {
    const keys: string[] = []
    const walk = (nodes: MenuRow[]) => {
      for (const n of nodes) {
        keys.push(n.id)
        if (n.children?.length) walk(n.children)
      }
    }
    walk(tree)
    return keys
  }, [tree])

  const openCreate = (parentId?: string | null) => {
    setEditingId(null)
    setInitialForm(null)
    setDefaultParentId(parentId ?? null)
    setDrawerOpen(true)
  }

  const openEdit = (row: SysMenuNode) => {
    setEditingId(row.id)
    setInitialForm(nodeToFormValues(row))
    setDefaultParentId(null)
    setDrawerOpen(true)
  }

  const handleSubmit = async (body: SysMenuCreateBody) => {
    setSubmitting(true)
    try {
      if (editingId) {
        await patchMenu(editingId, body)
        messageApi.success(t('menuConfig.updated'))
      } else {
        await createMenu(body)
        messageApi.success(t('menuConfig.created'))
      }
      setDrawerOpen(false)
      setRev((x) => x + 1)
      notifyMenuNavRefresh()
    } catch (e) {
      showAppError(messageApi, t, e)
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (row: SysMenuNode) => {
    try {
      const res = await deleteMenu(row.id)
      messageApi.success(t('menuConfig.deletedCount', { count: res.deleted_count }))
      setRev((x) => x + 1)
      notifyMenuNavRefresh()
    } catch (e) {
      showAppError(messageApi, t, e)
    }
  }

  const columns: ColumnsType<MenuRow> = useMemo(
    () => [
      {
        title: t('menuConfig.col.menuName'),
        dataIndex: 'menu_name',
        key: 'menu_name',
        width: 220,
        fixed: 'left',
        ellipsis: true,
      },
      {
        title: t('menuConfig.col.icon'),
        key: 'icon',
        width: 56,
        render: (_, row) => resolveMenuIcon(row.icon),
      },
      {
        title: t('menuConfig.col.orderNum'),
        dataIndex: 'order_num',
        key: 'order_num',
        width: 72,
      },
      {
        title: t('menuConfig.col.perms'),
        dataIndex: 'perms',
        key: 'perms',
        width: 160,
        ellipsis: true,
        render: (v: string | null) => v || '—',
      },
      {
        title: t('menuConfig.col.path'),
        dataIndex: 'path',
        key: 'path',
        width: 200,
        ellipsis: true,
        render: (v: string | null) => v || '—',
      },
      {
        title: t('menuConfig.col.status'),
        key: 'status',
        width: 88,
        render: (_, row) => (
          <Tag color={row.status ? 'success' : 'default'}>
            {row.status ? t('menuConfig.status.enabled') : t('menuConfig.status.disabled')}
          </Tag>
        ),
      },
      {
        title: t('menuConfig.col.createAt'),
        dataIndex: 'create_at',
        key: 'create_at',
        width: 170,
        render: (v: string | null) => (v ? v.slice(0, 19).replace('T', ' ') : '—'),
      },
      {
        title: t('menuConfig.col.actions'),
        key: 'actions',
        width: 112,
        fixed: 'right',
        render: (_, row) => {
          const childCount = countDescendants(row)
          return (
            <Space size={2}>
              <Tooltip title={t('menuConfig.edit')}>
                <Button
                  type="text"
                  size="small"
                  icon={<EditOutlined />}
                  onClick={() => openEdit(row)}
                  aria-label={t('menuConfig.edit')}
                />
              </Tooltip>
              <Tooltip title={t('menuConfig.addChild')}>
                <Button
                  type="text"
                  size="small"
                  icon={<PlusOutlined />}
                  onClick={() => openCreate(row.id)}
                  aria-label={t('menuConfig.addChild')}
                />
              </Tooltip>
              <Tooltip title={t('menuConfig.delete')}>
                <span>
                  <Popconfirm
                    title={t('menuConfig.deleteConfirm', { name: row.menu_name })}
                    description={
                      childCount > 0
                        ? t('menuConfig.deleteDesc', { count: childCount })
                        : t('menuConfig.deleteDescNone')
                    }
                    onConfirm={() => void handleDelete(row)}
                  >
                    <Button
                      type="text"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      aria-label={t('menuConfig.delete')}
                    />
                  </Popconfirm>
                </span>
              </Tooltip>
            </Space>
          )
        },
      },
    ],
    [t],
  )

  if (forbidden) {
    return <Result status="403" title={t('menuConfig.forbidden')} />
  }

  return (
    <div className="minerva-menu-config-page">
      <Card size="small" variant="borderless" className="minerva-menu-config-page__card">
        <Space className="minerva-menu-config-page__toolbar" wrap>
          <Input
            allowClear
            placeholder={t('menuConfig.searchName')}
            value={nameFilter}
            onChange={(e) => setNameFilter(e.target.value)}
            onPressEnter={() => setRev((x) => x + 1)}
            style={{ width: 200 }}
          />
          <Select
            allowClear
            placeholder={t('menuConfig.filterStatus')}
            style={{ width: 140 }}
            value={statusFilter}
            onChange={(v) => setStatusFilter(v)}
            options={[
              { value: true, label: t('menuConfig.status.enabled') },
              { value: false, label: t('menuConfig.status.disabled') },
            ]}
          />
          <Button onClick={() => setRev((x) => x + 1)}>{t('menuConfig.search')}</Button>
          <Button icon={<SwapOutlined />} onClick={() => setExpandedKeys(allKeys)}>
            {t('menuConfig.expandAll')}
          </Button>
          <Button onClick={() => setExpandedKeys([])}>{t('menuConfig.collapseAll')}</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openCreate(null)}>
            {t('menuConfig.add')}
          </Button>
        </Space>
        <div ref={tableWrapRef} className="minerva-menu-config-page__table-wrap">
          <Table<MenuRow>
            rowKey="id"
            loading={loading}
            columns={columns}
            dataSource={tree}
            pagination={false}
            size="middle"
            className="minerva-card-table-scroll-ocr minerva-menu-config-page__table"
            scroll={{ x: MENU_CONFIG_TABLE_SCROLL_X, y: tableBodyScrollY }}
            sticky
            expandable={{
              expandedRowKeys: expandedKeys,
              onExpandedRowsChange: (keys) => setExpandedKeys(keys as string[]),
            }}
          />
        </div>
      </Card>
      <MenuFormDrawer
        open={drawerOpen}
        title={editingId ? t('menuConfig.editTitle') : t('menuConfig.addTitle')}
        submitting={submitting}
        tree={tree}
        editingId={editingId}
        initial={initialForm}
        defaultParentId={defaultParentId}
        onClose={() => setDrawerOpen(false)}
        onSubmit={handleSubmit}
      />
    </div>
  )
}
