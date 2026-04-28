import { DeleteOutlined, EditOutlined, EyeOutlined, PlusOutlined } from '@ant-design/icons'
import {
  Button,
  Card,
  Cascader,
  Descriptions,
  Drawer,
  Form,
  Input,
  Popconfirm,
  Select,
  Space,
  Table,
  Tooltip,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  createRuleConfigPrompt,
  deleteRuleConfigPrompt,
  listRuleConfigPrompts,
  patchRuleConfigPrompt,
  type RuleConfigPromptListItem,
} from '@/api/ruleConfigPrompt'
import { listModelProviders, type ModelProviderListItem } from '@/api/modelProviders'
import { ApiError } from '@/api/client'
import { useAuth } from '@/app/AuthContext'
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'
import { useDictItemTree } from '@/hooks/useDictItemTree'
import {
  ENG_SUBJECT_DOC_DICT_CODE,
  dictNodesToCascaderOptions,
  findSequentialPathInTree,
  formatScopeTriplePathLabel,
  listParamsFromCascadePath,
  pathToTriple,
  tripleToPath,
  buildCodeNameMap,
} from '@/features/rules/scopeTriple'
import './RulesManagementPage.css'

type FormValues = {
  eng_subject_doc?: string[]
  model_id: string
  sys_prompt?: string | null
  user_prompt?: string | null
  chat_memory?: string | null
}

function showErr(t: (k: string) => string, e: unknown) {
  if (e instanceof ApiError) {
    void message.error(e.message)
    return
  }
  void message.error(t('common.error'))
}

export function RulesPromptManagementPage() {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const [form] = Form.useForm<FormValues>()
  const [loading, setLoading] = useState(false)
  const [rows, setRows] = useState<RuleConfigPromptListItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [models, setModels] = useState<ModelProviderListItem[]>([])
  const [modelsLoading, setModelsLoading] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailRow, setDetailRow] = useState<RuleConfigPromptListItem | null>(null)

  const engSubDocDictQ = useDictItemTree(ENG_SUBJECT_DOC_DICT_CODE)
  const flatItems = useMemo(() => engSubDocDictQ.data?.flat ?? [], [engSubDocDictQ.data])
  const cascaderTree = useMemo(() => engSubDocDictQ.data?.itemTree ?? [], [engSubDocDictQ.data])
  const cascaderOptions = useMemo(() => dictNodesToCascaderOptions(cascaderTree), [cascaderTree])
  const dictLoading = engSubDocDictQ.isLoading
  const [qEngSubjectDoc, setQEngSubjectDoc] = useState<string[] | undefined>(undefined)
  const [appliedEngSubjectDoc, setAppliedEngSubjectDoc] = useState<string[] | undefined>(
    undefined,
  )

  const engSubDocNameMap = useMemo(() => buildCodeNameMap(flatItems), [flatItems])

  const loadModels = useCallback(async () => {
    if (!workspaceId) return
    setModelsLoading(true)
    try {
      const list = await listModelProviders(workspaceId)
      setModels(list)
    } catch (e) {
      showErr(t, e)
    } finally {
      setModelsLoading(false)
    }
  }, [workspaceId, t])

  const loadList = useCallback(async () => {
    if (!workspaceId) return
    setLoading(true)
    try {
      const cascadeParams = listParamsFromCascadePath(appliedEngSubjectDoc)
      const data = await listRuleConfigPrompts(workspaceId, {
        page,
        page_size: DEFAULT_PAGE_SIZE,
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
  }, [workspaceId, page, t, appliedEngSubjectDoc])

  useEffect(() => {
    if (!engSubDocDictQ.isSuccess) return
    if (!engSubDocDictQ.data?.listRow) void message.warning(t('rules.missingDictEngSubjectDoc'))
  }, [engSubDocDictQ.isSuccess, engSubDocDictQ.data?.listRow, t])

  useEffect(() => {
    if (engSubDocDictQ.isError) showErr(t, engSubDocDictQ.error)
  }, [engSubDocDictQ.isError, engSubDocDictQ.error, t])

  useEffect(() => {
    void loadModels()
  }, [loadModels])

  useEffect(() => {
    void loadList()
  }, [loadList, workspaceId])

  const runSearch = useCallback(() => {
    setAppliedEngSubjectDoc(qEngSubjectDoc?.length ? [...qEngSubjectDoc] : undefined)
    setPage(1)
  }, [qEngSubjectDoc])

  const resetFilters = useCallback(() => {
    setQEngSubjectDoc(undefined)
    setAppliedEngSubjectDoc(undefined)
    setPage(1)
  }, [])

  const openCreate = useCallback(() => {
    setEditingId(null)
    form.resetFields()
    form.setFieldsValue({
      eng_subject_doc: undefined,
      model_id: undefined,
      sys_prompt: '',
      user_prompt: '',
      chat_memory: '',
    })
    setOpen(true)
  }, [form])

  const openDetail = useCallback((row: RuleConfigPromptListItem) => {
    setDetailRow(row)
    setDetailOpen(true)
  }, [])

  const openEdit = useCallback(
    (row: RuleConfigPromptListItem) => {
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
        eng_subject_doc: path,
        model_id: row.model_id,
        sys_prompt: row.sys_prompt ?? '',
        user_prompt: row.user_prompt ?? '',
        chat_memory: row.chat_memory ?? '',
      })
      setOpen(true)
    },
    [cascaderTree, form],
  )

  const onSubmit = useCallback(async () => {
    if (!workspaceId) return
    try {
      const v = await form.validateFields()
      setSubmitting(true)
      const { engineering_code, subject_code, document_type } = pathToTriple(v.eng_subject_doc)
      const body = {
        model_id: v.model_id,
        engineering_code,
        subject_code,
        document_type,
        sys_prompt: v.sys_prompt?.trim() || null,
        user_prompt: v.user_prompt?.trim() || null,
        chat_memory: v.chat_memory?.trim() || null,
      }
      if (editingId) {
        await patchRuleConfigPrompt(workspaceId, editingId, body)
        void message.success(t('rules.promptUpdateSuccess'))
      } else {
        await createRuleConfigPrompt(workspaceId, body)
        void message.success(t('rules.promptCreateSuccess'))
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
        await deleteRuleConfigPrompt(workspaceId, id)
        void message.success(t('rules.promptDeleted'))
        await loadList()
      } catch (e) {
        showErr(t, e)
      }
    },
    [loadList, t, workspaceId],
  )

  const timeCell = (v: string | null) =>
    v ? new Date(v).toLocaleString(undefined, { hour12: false }) : '—'

  const modelOptions = useMemo(
    () =>
      models.map((m) => ({
        value: m.id,
        label: `${m.provider_name} / ${m.model_name}`,
      })),
    [models],
  )

  const columns: ColumnsType<RuleConfigPromptListItem> = useMemo(
    () => [
      {
        title: t('rules.colEngSubjectDoc'),
        key: 'scope',
        width: 330,
        ellipsis: { showTitle: true },
        render: (_, row) => formatScopeTriplePathLabel(row, engSubDocNameMap),
      },
      {
        title: t('rules.promptColModel'),
        key: 'model',
        width: 200,
        ellipsis: { showTitle: true },
        render: (_, row) => `${row.provider_name} / ${row.model_name}`,
      },
      {
        title: t('rules.promptColSysPrompt'),
        dataIndex: 'sys_prompt',
        ellipsis: { showTitle: true },
        render: (c: string | null) => c ?? '—',
      },
      {
        title: t('rules.promptColUserPrompt'),
        dataIndex: 'user_prompt',
        ellipsis: { showTitle: true },
        render: (c: string | null) => c ?? '—',
      },
      {
        title: t('rules.colUpdated'),
        dataIndex: 'update_at',
        width: 168,
        render: timeCell,
      },
      {
        title: t('rules.colActions'),
        key: 'actions',
        width: 120,
        fixed: 'end',
        render: (_, row) => (
          <Space size={4}>
            <Tooltip title={t('rules.viewDetail')}>
              <Button
                type="text"
                size="small"
                icon={<EyeOutlined />}
                onClick={() => openDetail(row)}
                aria-label={t('rules.viewDetail')}
              />
            </Tooltip>
            <Tooltip title={t('rules.edit')}>
              <Button
                type="text"
                size="small"
                icon={<EditOutlined />}
                onClick={() => openEdit(row)}
                aria-label={t('rules.edit')}
              />
            </Tooltip>
            <Popconfirm title={t('rules.promptDeleteConfirm')} onConfirm={() => onDelete(row.id)}>
              <Button
                type="text"
                size="small"
                danger
                icon={<DeleteOutlined />}
                aria-label={t('rules.delete')}
              />
            </Popconfirm>
          </Space>
        ),
      },
    ],
    [engSubDocNameMap, onDelete, openDetail, openEdit, t],
  )

  return (
    <div className="minerva-rules-page">
      <Card className="minerva-rules-page__card" variant="borderless" style={{ minHeight: 0 }}>
        <div className="minerva-rules-page__toolbar">
          <Button
            type="primary"
            icon={<PlusOutlined />}
            className="minerva-rules-page__add-btn"
            onClick={openCreate}
            disabled={dictLoading}
          >
            {t('rules.promptToolbarAdd')}
          </Button>
          <Cascader
            allowClear
            changeOnSelect
            className="minerva-rules-page__filter minerva-rules-page__filter--cascade"
            options={cascaderOptions}
            placeholder={t('rules.filterEngSubjectDoc')}
            value={qEngSubjectDoc}
            onChange={(v) => setQEngSubjectDoc(v as string[] | undefined)}
            loading={dictLoading}
            showSearch={{ matchInputWidth: false }}
            displayRender={(labels) => (labels.length ? labels.join(' / ') : '')}
          />
          <Button onClick={runSearch}>{t('rules.search')}</Button>
          <Button onClick={resetFilters}>{t('rules.resetFilter')}</Button>
        </div>
        <div className="minerva-rules-page__table-wrap">
          <Table<RuleConfigPromptListItem>
            className="minerva-card-table-scroll-ocr minerva-rules-page__table"
            size="small"
            rowKey="id"
            loading={loading}
            columns={columns}
            dataSource={rows}
            scroll={{ x: 1280, y: 'calc(100dvh - 400px)' }}
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
        title={editingId ? t('rules.promptDrawerEdit') : t('rules.promptDrawerCreate')}
        width={520}
        open={open}
        onClose={() => setOpen(false)}
        destroyOnHidden
        className="minerva-rules-drawer"
        classNames={{ body: 'minerva-scrollbar-styled' }}
        footer={
          <Space style={{ float: 'right' }}>
            <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
            <Button type="primary" loading={submitting} onClick={() => void onSubmit()}>
              {t('common.save')}
            </Button>
          </Space>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item name="eng_subject_doc" label={t('rules.fieldEngSubjectDoc')}>
            <Cascader
              allowClear
              changeOnSelect
              options={cascaderOptions}
              placeholder={t('rules.fieldEngSubjectDocPlaceholder')}
              loading={dictLoading}
              showSearch
            />
          </Form.Item>
          <Form.Item
            name="model_id"
            label={t('rules.promptFieldModel')}
            rules={[{ required: true, message: t('rules.promptModelRequired') }]}
          >
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              loading={modelsLoading}
              options={modelOptions}
              placeholder={t('rules.promptFieldModel')}
            />
          </Form.Item>
          <Form.Item name="sys_prompt" label={t('rules.promptFieldSysPrompt')}>
            <Input.TextArea
              allowClear
              rows={4}
              maxLength={1024}
              showCount
              classNames={{ textarea: 'minerva-scrollbar-styled' }}
            />
          </Form.Item>
          <Form.Item name="user_prompt" label={t('rules.promptFieldUserPrompt')}>
            <Input.TextArea
              allowClear
              rows={4}
              classNames={{ textarea: 'minerva-scrollbar-styled' }}
            />
          </Form.Item>
          <Form.Item name="chat_memory" label={t('rules.promptFieldChatMemory')}>
            <Input.TextArea
              allowClear
              rows={3}
              classNames={{ textarea: 'minerva-scrollbar-styled' }}
            />
          </Form.Item>
        </Form>
      </Drawer>

      <Drawer
        className="minerva-rules-drawer"
        title={t('rules.promptDetailTitle')}
        open={detailOpen}
        onClose={() => {
          setDetailOpen(false)
          setDetailRow(null)
        }}
        width="50%"
        classNames={{ body: 'minerva-scrollbar-styled' }}
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
          <Descriptions
            bordered
            column={1}
            size="small"
            className="minerva-rules-drawer-details"
          >
            <Descriptions.Item label={t('rules.detailEngSubjectDoc')}>
              {formatScopeTriplePathLabel(detailRow, engSubDocNameMap)}
            </Descriptions.Item>
            <Descriptions.Item label={t('rules.promptFieldModel')}>
              {`${detailRow.provider_name} / ${detailRow.model_name}`}
            </Descriptions.Item>
            <Descriptions.Item label={t('rules.promptFieldSysPrompt')}>
              {detailRow.sys_prompt ?? '—'}
            </Descriptions.Item>
            <Descriptions.Item label={t('rules.promptFieldUserPrompt')}>
              {detailRow.user_prompt ?? '—'}
            </Descriptions.Item>
            <Descriptions.Item label={t('rules.promptFieldChatMemory')}>
              {detailRow.chat_memory ?? '—'}
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
