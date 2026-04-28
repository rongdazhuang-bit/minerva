import {
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  PlusOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import {
  Button,
  Card,
  Cascader,
  Col,
  Descriptions,
  Drawer,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tooltip,
  message,
} from 'antd'
import type { DefaultOptionType } from 'antd/es/cascader'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { SysDictItem, SysDictItemNode } from '@/api/dicts'
import { useDictItemTree } from '@/hooks/useDictItemTree'
import {
  createRuleBase,
  deleteRuleBase,
  listRuleBase,
  patchRuleBase,
  polishReviewRules,
  type ListRuleBaseParams,
  type RuleBaseListItem,
} from '@/api/ruleBase'
import { ApiError } from '@/api/client'
import { useAuth } from '@/app/AuthContext'
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'
import './RulesManagementPage.css'

/** 多级字典：第 1～3 级 code 依次对应 engineering_code / subject_code / document_type */
const ENG_SUBJECT_DOC_DICT_CODE = 'RULE_ENG_SUBJECT_DOC'

type FormValues = {
  sequence_number: number
  eng_subject_doc?: string[]
  serial_number?: string | null
  review_section: string
  review_object: string
  review_rules: string
  review_rules_ai?: string | null
  review_result: string
  status: 'Y' | 'N'
}

function showErr(t: (k: string) => string, e: unknown) {
  if (e instanceof ApiError) {
    void message.error(e.message)
    return
  }
  void message.error(t('common.error'))
}

function buildCodeNameMap(items: SysDictItem[]) {
  const m = new Map<string, string>()
  for (const it of items) {
    m.set(it.code, it.name)
  }
  return m
}

function dictNodesToCascaderOptions(nodes: SysDictItemNode[]): DefaultOptionType[] {
  return nodes.map((n) => ({
    value: n.code,
    label: n.name,
    children: n.children?.length ? dictNodesToCascaderOptions(n.children) : undefined,
  }))
}

function pathToTriple(path: string[] | undefined | null) {
  const p = path?.filter((x) => x != null && String(x).trim() !== '') ?? []
  return {
    engineering_code: p[0] ?? null,
    subject_code: p[1] ?? null,
    document_type: p[2] ?? null,
  }
}

function tripleToPath(
  eng: string | null | undefined,
  sub: string | null | undefined,
  doc: string | null | undefined,
): string[] | undefined {
  if (!eng?.trim()) return undefined
  const e = eng.trim()
  const out: string[] = [e]
  if (sub?.trim()) {
    out.push(sub.trim())
    if (doc?.trim()) out.push(doc.trim())
  }
  return out
}

function listParamsFromCascadePath(
  path: string[] | undefined,
): Pick<ListRuleBaseParams, 'engineering_code' | 'subject_code' | 'document_type'> {
  const p = path?.filter(Boolean) ?? []
  const o: Pick<ListRuleBaseParams, 'engineering_code' | 'subject_code' | 'document_type'> =
    {}
  if (p.length >= 1) o.engineering_code = p[0]
  if (p.length >= 2) o.subject_code = p[1]
  if (p.length >= 3) o.document_type = p[2]
  return o
}

function formatTriplePathLabel(row: RuleBaseListItem, nameByCode: Map<string, string>) {
  const parts: string[] = []
  for (const c of [row.engineering_code, row.subject_code, row.document_type]) {
    if (!c) continue
    parts.push(nameByCode.get(c) ?? c)
  }
  return parts.length ? parts.join(' / ') : '—'
}

/** 在非空编码序列上与树前缀匹配，兼容仅有专业/文档类型等业务旧数据时的回显。 */
function findSequentialPathInTree(
  nodes: SysDictItemNode[],
  codes: string[],
): string[] | undefined {
  if (!codes.length || !nodes.length) return undefined
  const walk = (
    arr: SysDictItemNode[],
    depth: number,
    acc: string[],
  ): string[] | undefined => {
    const code = codes[depth]
    for (const n of arr) {
      if (n.code !== code) continue
      const next = [...acc, n.code]
      if (depth === codes.length - 1) return next
      const sub = walk(n.children ?? [], depth + 1, next)
      if (sub) return sub
    }
    return undefined
  }
  return walk(nodes, 0, [])
}

export function RulesManagementPage() {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const [form] = Form.useForm<FormValues>()
  const [loading, setLoading] = useState(false)
  const [rows, setRows] = useState<RuleBaseListItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [polishingRules, setPolishingRules] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailRow, setDetailRow] = useState<RuleBaseListItem | null>(null)
  const engSubDocDictQ = useDictItemTree(ENG_SUBJECT_DOC_DICT_CODE)
  const flatItems = useMemo(() => engSubDocDictQ.data?.flat ?? [], [engSubDocDictQ.data])
  const cascaderTree = useMemo(() => engSubDocDictQ.data?.itemTree ?? [], [engSubDocDictQ.data])
  const cascaderOptions = useMemo(() => dictNodesToCascaderOptions(cascaderTree), [cascaderTree])
  const dictLoading = engSubDocDictQ.isLoading
  const [statusSavingId, setStatusSavingId] = useState<string | null>(null)
  /** 搜索栏多级路径（点「搜索」后写入 applied） */
  const [qEngSubjectDoc, setQEngSubjectDoc] = useState<string[] | undefined>(undefined)
  const [qStatus, setQStatus] = useState<'Y' | 'N' | undefined>(undefined)
  const [appliedEngSubjectDoc, setAppliedEngSubjectDoc] = useState<string[] | undefined>(
    undefined,
  )
  const [appliedStatus, setAppliedStatus] = useState<'Y' | 'N' | undefined>(undefined)

  const engSubDocNameMap = useMemo(() => buildCodeNameMap(flatItems), [flatItems])

  const loadList = useCallback(async () => {
    if (!workspaceId) return
    setLoading(true)
    try {
      const cascadeParams = listParamsFromCascadePath(appliedEngSubjectDoc)
      const data = await listRuleBase(workspaceId, {
        page,
        page_size: DEFAULT_PAGE_SIZE,
        status: appliedStatus,
        ...cascadeParams,
      })
      setRows(data.items)
      setTotal(data.total)
      const maxPage = Math.max(1, Math.ceil(data.total / DEFAULT_PAGE_SIZE) || 1)
      if (page > maxPage) setPage(maxPage)
    } catch (e) {
      showErr(t, e)
    } finally {
      setLoading(false)
    }
  }, [workspaceId, page, t, appliedEngSubjectDoc, appliedStatus])

  useEffect(() => {
    if (!engSubDocDictQ.isSuccess) return
    if (!engSubDocDictQ.data?.listRow) void message.warning(t('rules.missingDictEngSubjectDoc'))
  }, [engSubDocDictQ.isSuccess, engSubDocDictQ.data?.listRow, t])

  useEffect(() => {
    if (engSubDocDictQ.isError) showErr(t, engSubDocDictQ.error)
  }, [engSubDocDictQ.isError, engSubDocDictQ.error, t])

  useEffect(() => {
    void loadList()
  }, [loadList, workspaceId])

  const runSearch = useCallback(() => {
    setAppliedEngSubjectDoc(qEngSubjectDoc?.length ? [...qEngSubjectDoc] : undefined)
    setAppliedStatus(qStatus)
    setPage(1)
  }, [qEngSubjectDoc, qStatus])

  const resetFilters = useCallback(() => {
    setQEngSubjectDoc(undefined)
    setQStatus(undefined)
    setAppliedEngSubjectDoc(undefined)
    setAppliedStatus(undefined)
    setPage(1)
  }, [])

  const runAiPolish = useCallback(async () => {
    if (!workspaceId) return
    const rules = form.getFieldValue('review_rules') as string | undefined
    if (!rules?.trim()) {
      void message.warning(t('rules.aiPolishNeedRules'))
      return
    }
    setPolishingRules(true)
    try {
      const { review_rules_ai } = await polishReviewRules(workspaceId, {
        review_rules: rules,
      })
      form.setFieldValue('review_rules_ai', review_rules_ai)
      void message.success(t('rules.aiPolishSuccess'))
    } catch (e) {
      showErr(t, e)
    } finally {
      setPolishingRules(false)
    }
  }, [form, t, workspaceId])

  const openCreate = useCallback(() => {
    setEditingId(null)
    form.resetFields()
    form.setFieldsValue({
      sequence_number: 0,
      status: 'Y',
      eng_subject_doc: undefined,
      review_section: '',
      review_object: '',
      review_rules: '',
      review_rules_ai: '',
      review_result: '',
    })
    setOpen(true)
  }, [form])

  const openEdit = useCallback(
    (row: RuleBaseListItem) => {
      setEditingId(row.id)
      const fromTriple = tripleToPath(
        row.engineering_code ?? null,
        row.subject_code,
        row.document_type,
      )
      const codesTrim = [
        row.engineering_code,
        row.subject_code,
        row.document_type,
      ].filter((c): c is string => typeof c === 'string' && c.trim().length > 0)
      const path =
        fromTriple ??
        (codesTrim.length
          ? findSequentialPathInTree(cascaderTree, codesTrim)
          : undefined)
      form.setFieldsValue({
        sequence_number: row.sequence_number,
        eng_subject_doc: path,
        serial_number: row.serial_number,
        review_section: row.review_section,
        review_object: row.review_object,
        review_rules: row.review_rules,
        review_rules_ai: row.review_rules_ai ?? '',
        review_result: row.review_result,
        status: row.status === 'N' ? 'N' : 'Y',
      })
      setOpen(true)
    },
    [cascaderTree, form],
  )

  const openDetail = useCallback((row: RuleBaseListItem) => {
    setDetailRow(row)
    setDetailOpen(true)
  }, [])

  const onSubmit = useCallback(async () => {
    if (!workspaceId) return
    try {
      const v = await form.validateFields()
      setSubmitting(true)
      const { engineering_code, subject_code, document_type } = pathToTriple(v.eng_subject_doc)
      const body = {
        sequence_number: v.sequence_number,
        engineering_code,
        subject_code,
        serial_number: v.serial_number?.trim() || null,
        document_type,
        review_section: v.review_section.trim(),
        review_object: v.review_object.trim(),
        review_rules: v.review_rules.trim(),
        review_rules_ai: v.review_rules_ai?.trim() || null,
        review_result: v.review_result.trim(),
        status: v.status,
      }
      if (editingId) {
        await patchRuleBase(workspaceId, editingId, body)
        void message.success(t('rules.updateSuccess'))
      } else {
        await createRuleBase(workspaceId, body)
        void message.success(t('rules.createSuccess'))
      }
      setOpen(false)
      await loadList()
    } catch (e) {
      if (e && typeof e === 'object' && 'errorFields' in (e as object)) return
      showErr(t, e)
    } finally {
      setSubmitting(false)
    }
  }, [editingId, form, loadList, t, workspaceId])

  const onDelete = useCallback(
    async (id: string) => {
      if (!workspaceId) return
      try {
        await deleteRuleBase(workspaceId, id)
        void message.success(t('rules.deleted'))
        await loadList()
      } catch (e) {
        showErr(t, e)
      }
    },
    [loadList, t, workspaceId],
  )

  const onToggleStatus = useCallback(
    async (row: RuleBaseListItem, checked: boolean) => {
      if (!workspaceId) return
      const next: 'Y' | 'N' = checked ? 'Y' : 'N'
      const cur: 'Y' | 'N' = row.status === 'N' ? 'N' : 'Y'
      if (next === cur) return
      setStatusSavingId(row.id)
      try {
        await patchRuleBase(workspaceId, row.id, { status: next })
        setRows((prev) => prev.map((r) => (r.id === row.id ? { ...r, status: next } : r)))
        void message.success(t('rules.updateSuccess'))
      } catch (e) {
        showErr(t, e)
      } finally {
        setStatusSavingId(null)
      }
    },
    [t, workspaceId],
  )

  const timeCell = (v: string | null) =>
    v ? new Date(v).toLocaleString(undefined, { hour12: false }) : '—'

  const columns: ColumnsType<RuleBaseListItem> = useMemo(
    () => [
      {
        title: t('rules.colSequence'),
        dataIndex: 'sequence_number',
        width: 80,
        fixed: 'left',
        ellipsis: { showTitle: true },
      },
      {
        title: t('rules.colSerial'),
        dataIndex: 'serial_number',
        width: 100,
        fixed: 'left',
        ellipsis: { showTitle: true },
        render: (c: string | null) => c ?? '—',
      },
      {
        title: t('rules.colEngSubjectDoc'),
        key: 'eng_subject_doc',
        width: 260,
        fixed: 'left',
        ellipsis: { showTitle: true },
        render: (_, row) => formatTriplePathLabel(row, engSubDocNameMap),
      },
      {
        title: t('rules.colSection'),
        dataIndex: 'review_section',
        width: 210,
        ellipsis: { showTitle: true },
      },
      {
        title: t('rules.colObject'),
        dataIndex: 'review_object',
        width: 210,
        ellipsis: { showTitle: true },
      },
      {
        title: t('rules.colRules'),
        dataIndex: 'review_rules',
        width: 270,
        ellipsis: { showTitle: true },
      },
      {
        title: t('rules.colResult'),
        dataIndex: 'review_result',
        width: 270,
        ellipsis: { showTitle: true },
      },
      {
        title: t('rules.colStatus'),
        dataIndex: 'status',
        width: 88,
        render: (s: string, row) => (
          <Switch
            size="small"
            checked={s !== 'N'}
            loading={statusSavingId === row.id}
            disabled={statusSavingId !== null && statusSavingId !== row.id}
            onChange={(ch) => void onToggleStatus(row, ch)}
            aria-label={t('rules.fieldStatus')}
          />
        ),
      },
      {
        title: t('rules.colCreated'),
        dataIndex: 'create_at',
        width: 180,
        ellipsis: { showTitle: true },
        render: timeCell,
      },
      {
        title: t('rules.colUpdated'),
        dataIndex: 'update_at',
        width: 180,
        ellipsis: { showTitle: true },
        render: timeCell,
      },
      {
        title: t('rules.colActions'),
        key: 'actions',
        width: 176,
        fixed: 'right',
        render: (_, row) => (
          <Space>
            <Button
              type="text"
              icon={<EyeOutlined />}
              onClick={() => openDetail(row)}
              aria-label={t('rules.viewDetail')}
            />
            <Button
              type="text"
              icon={<EditOutlined />}
              onClick={() => openEdit(row)}
              aria-label={t('rules.edit')}
            />
            <Popconfirm title={t('rules.deleteConfirm')} onConfirm={() => void onDelete(row.id)}>
              <Button
                type="text"
                danger
                icon={<DeleteOutlined />}
                aria-label={t('rules.delete')}
              />
            </Popconfirm>
          </Space>
        ),
      },
    ],
    [
      engSubDocNameMap,
      onDelete,
      onToggleStatus,
      openDetail,
      openEdit,
      statusSavingId,
      t,
    ],
  )

  const statusFilterOptions = useMemo(
    () => [
      { value: 'Y' as const, label: t('rules.statusY') },
      { value: 'N' as const, label: t('rules.statusN') },
    ],
    [t],
  )

  if (!workspaceId) {
    return null
  }

  return (
    <div className="minerva-rules-page">
      <Card className="minerva-rules-page__card" variant="borderless" style={{ minHeight: 0 }}>
        <div className="minerva-rules-page__toolbar">
          <Button
            className="minerva-rules-page__add-btn"
            type="primary"
            icon={<PlusOutlined />}
            onClick={openCreate}
            disabled={dictLoading}
          >
            {t('rules.toolbarAdd')}
          </Button>
          <Cascader
            className="minerva-rules-page__filter minerva-rules-page__filter--cascade"
            allowClear
            showSearch={{ matchInputWidth: false }}
            changeOnSelect
            loading={dictLoading}
            placeholder={t('rules.filterEngSubjectDoc')}
            options={cascaderOptions}
            value={qEngSubjectDoc}
            onChange={(v) => setQEngSubjectDoc(v as string[] | undefined)}
            displayRender={(labels) =>
              labels.length ? labels.join(' / ') : ''
            }
          />
          <Select
            className="minerva-rules-page__filter minerva-rules-page__filter--status"
            allowClear
            placeholder={t('rules.filterStatus')}
            value={qStatus}
            onChange={(v) => setQStatus(v === 'Y' || v === 'N' ? v : undefined)}
            options={statusFilterOptions}
          />
          <Button onClick={runSearch}>{t('rules.search')}</Button>
          <Button onClick={resetFilters}>{t('rules.resetFilter')}</Button>
        </div>
        <div className="minerva-rules-page__table-wrap">
          <Table<RuleBaseListItem>
            className="minerva-rules-page__table"
            size="small"
            rowKey="id"
            loading={loading}
            columns={columns}
            dataSource={rows}
            tableLayout="fixed"
            scroll={{ x: 'max-content', y: 420 }}
            sticky
            pagination={{
              current: page,
              pageSize: DEFAULT_PAGE_SIZE,
              total,
              showSizeChanger: false,
              onChange: (p) => setPage(p),
            }}
          />
        </div>
      </Card>

      <Drawer
        className="minerva-rules-drawer"
        title={editingId ? t('rules.drawerEdit') : t('rules.drawerCreate')}
        open={open}
        onClose={() => setOpen(false)}
        width="50%"
        destroyOnClose
        styles={{ body: { paddingBottom: 8 } }}
        footer={
          <Space style={{ justifyContent: 'flex-end', width: '100%' }}>
            <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
            <Button type="primary" loading={submitting} onClick={() => void onSubmit()}>
              {t('common.save')}
            </Button>
          </Space>
        }
      >
        <Form form={form} layout="vertical" requiredMark>
          <Row gutter={[20, 4]}>
            <Col xs={24} md={12}>
              <Form.Item
                name="sequence_number"
                label={t('rules.fieldSequence')}
                rules={[{ required: true, message: t('rules.sequenceRequired') }]}
              >
                <InputNumber style={{ width: '100%' }} min={-32768} max={32767} step={1} />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="serial_number" label={t('rules.fieldSerial')}>
                <Input allowClear maxLength={32} />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="eng_subject_doc" label={t('rules.fieldEngSubjectDoc')}>
                <Cascader
                  allowClear
                  showSearch={{ matchInputWidth: false }}
                  changeOnSelect
                  loading={dictLoading}
                  style={{ width: '100%' }}
                  options={cascaderOptions}
                  placeholder={t('rules.fieldEngSubjectDocPlaceholder')}
                  displayRender={(labels) =>
                    labels.length ? labels.join(' / ') : ''
                  }
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item
                name="review_section"
                label={t('rules.fieldSection')}
                rules={[{ required: true, message: t('rules.fieldSection') }]}
              >
                <Input allowClear maxLength={128} />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item
                name="review_object"
                label={t('rules.fieldObject')}
                rules={[{ required: true, message: t('rules.fieldObject') }]}
              >
                <Input allowClear maxLength={128} />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item
                name="review_rules"
                label={
                  <span className="minerva-rules-form__inline-label">
                    <span>{t('rules.fieldRules')}</span>
                    <Tooltip title={t('rules.aiPolish')}>
                      <Button
                        type="text"
                        size="small"
                        className="minerva-rules-form__ai-btn"
                        icon={<ThunderboltOutlined />}
                        loading={polishingRules}
                        onClick={() => void runAiPolish()}
                        aria-label={t('rules.aiPolish')}
                      />
                    </Tooltip>
                  </span>
                }
                rules={[{ required: true, message: t('rules.fieldRules') }]}
              >
                <Input.TextArea allowClear rows={4} />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="review_rules_ai" label={t('rules.fieldRulesAi')}>
                <Input.TextArea allowClear rows={4} />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item
                name="review_result"
                label={t('rules.fieldResult')}
                rules={[{ required: true, message: t('rules.fieldResult') }]}
              >
                <Input.TextArea allowClear rows={4} />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item
                name="status"
                label={t('rules.fieldStatus')}
                rules={[{ required: true, message: t('rules.fieldStatus') }]}
              >
                <Select
                  allowClear={false}
                  style={{ maxWidth: 360 }}
                  options={[
                    { value: 'Y', label: t('rules.statusY') },
                    { value: 'N', label: t('rules.statusN') },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Drawer>

      <Drawer
        className="minerva-rules-drawer"
        title={t('rules.detailTitle')}
        open={detailOpen}
        onClose={() => {
          setDetailOpen(false)
          setDetailRow(null)
        }}
        width="50%"
        footer={
          <div style={{ textAlign: 'right' }}>
            <Button
              onClick={() => {
                setDetailOpen(false)
                setDetailRow(null)
              }}
            >
              {t('common.close')}
            </Button>
          </div>
        }
      >
        {detailRow ? (
          <Descriptions bordered column={1} size="small">
            <Descriptions.Item label={t('rules.fieldSequence')}>
              {detailRow.sequence_number}
            </Descriptions.Item>
            <Descriptions.Item label={t('rules.fieldSerial')}>
              {detailRow.serial_number ?? '—'}
            </Descriptions.Item>
            <Descriptions.Item label={t('rules.detailEngSubjectDoc')}>
              {formatTriplePathLabel(detailRow, engSubDocNameMap)}
            </Descriptions.Item>
            <Descriptions.Item label={t('rules.fieldSection')}>
              {detailRow.review_section}
            </Descriptions.Item>
            <Descriptions.Item label={t('rules.fieldObject')}>
              {detailRow.review_object}
            </Descriptions.Item>
            <Descriptions.Item label={t('rules.fieldRules')}>
              {detailRow.review_rules}
            </Descriptions.Item>
            <Descriptions.Item label={t('rules.fieldRulesAi')}>
              {detailRow.review_rules_ai ?? '—'}
            </Descriptions.Item>
            <Descriptions.Item label={t('rules.fieldResult')}>
              {detailRow.review_result}
            </Descriptions.Item>
            <Descriptions.Item label={t('rules.fieldStatus')}>
              {detailRow.status === 'N' ? t('rules.statusN') : t('rules.statusY')}
            </Descriptions.Item>
            <Descriptions.Item label={t('rules.colCreated')}>
              {timeCell(detailRow.create_at)}
            </Descriptions.Item>
            <Descriptions.Item label={t('rules.colUpdated')}>
              {timeCell(detailRow.update_at)}
            </Descriptions.Item>
          </Descriptions>
        ) : null}
      </Drawer>
    </div>
  )
}
