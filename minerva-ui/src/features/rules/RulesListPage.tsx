import { getRule, addRuleVersion, createRule, listRules, publishVersion } from '@/api/rules'
import { startExecution } from '@/api/executions'
import { ApiError } from '@/api/client'
import type { RuleListItem } from '@/api/types'
import { useAuth } from '@/app/AuthContext'
import { Button, Form, Input, Modal, Select, Table, Tag, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

const RULE_TYPES = [
  { value: 'document_review', label: 'document_review' },
  { value: 'workflow', label: 'workflow' },
  { value: 'policy', label: 'policy' },
]

export function RulesListPage() {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const nav = useNavigate()
  const [data, setData] = useState<RuleListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [open, setOpen] = useState(false)
  const [f] = Form.useForm()
  const load = useCallback(async () => {
    if (!workspaceId) return
    setLoading(true)
    try {
      setData(await listRules(workspaceId))
    } catch (e) {
      if (e instanceof ApiError) void message.error(e.message)
    } finally {
      setLoading(false)
    }
  }, [workspaceId])

  useEffect(() => {
    void load()
  }, [load])

  const onCreate = useCallback(
    (values: { name: string; type: string }) => {
      if (!workspaceId) return
      void (async () => {
        try {
          const r = await createRule(workspaceId, { name: values.name, type: values.type, flow_json: {} })
          void message.success('ok')
          setOpen(false)
          f.resetFields()
          void load()
          void nav(`/app/rules/${r.id}/edit`)
        } catch (e) {
          if (e instanceof ApiError) void message.error(e.message)
        }
      })()
    },
    [f, load, nav, workspaceId],
  )

  const runQuick = (row: RuleListItem) => {
    if (!workspaceId) return
    if (!row.current_published_version_id) {
      void message.warning('请先发布规则后再运行')
      return
    }
    void (async () => {
      const hide = message.loading('运行中…', 0)
      try {
        const ex = await startExecution(workspaceId, { rule_id: row.id, input: {} })
        void message.success('已启动执行', 1.5)
        void nav(`/app/executions/${ex.id}`)
      } catch (e) {
        if (e instanceof ApiError) void message.error(e.message)
      } finally {
        hide()
      }
    })()
  }

  const tryPublish = (row: RuleListItem) => {
    if (!workspaceId) return
    void (async () => {
      const hide = message.loading('发布中…', 0)
      try {
        const d = await getRule(workspaceId, row.id)
        if (!d.latest_version) {
          void message.warning('无版本可发布')
          return
        }
        if (d.latest_version.state === 'published') {
          void message.info('已发布')
          return
        }
        await publishVersion(workspaceId, row.id, d.latest_version.id)
        void message.success('已发布')
        void load()
      } catch (e) {
        if (e instanceof ApiError) void message.error(e.message)
      } finally {
        hide()
      }
    })()
  }

  const saveDefaultFlow = (row: RuleListItem) => {
    if (!workspaceId) return
    const flow = {
      schema_version: 1,
      nodes: [
        { id: 'a', type: 'start', data: {} },
        { id: 'b', type: 'end', data: {} },
      ],
      edges: [{ id: 'e1', source: 'a', target: 'b' }],
    }
    void (async () => {
      try {
        await addRuleVersion(workspaceId, row.id, flow)
        const d = await getRule(workspaceId, row.id)
        if (d.latest_version) {
          await publishVersion(workspaceId, row.id, d.latest_version.id)
        }
        void message.success('已准备默认图并发布')
        void load()
      } catch (e) {
        if (e instanceof ApiError) void message.error(e.message)
      }
    })()
  }

  const columns: ColumnsType<RuleListItem> = [
    { title: t('rules.name'), dataIndex: 'name', key: 'name' },
    { title: t('rules.type'), dataIndex: 'type', key: 'type', width: 180 },
    {
      title: t('rules.published'),
      key: 'pub',
      width: 100,
      render: (_, r) =>
        r.current_published_version_id ? <Tag color="success">Y</Tag> : <Tag>{t('rules.draft')}</Tag>,
    },
    {
      title: ' ',
      key: 'act',
      width: 360,
      render: (_, r) => (
        <>
          <Button type="link" size="small" onClick={() => void nav(`/app/rules/${r.id}/edit`)}>
            {t('rules.openDesigner')}
          </Button>
          <Button
            type="link"
            size="small"
            onClick={() => {
              Modal.confirm({
                title: '未发布时可用一键生成 start→end 并发布，是否继续？',
                onOk: () => saveDefaultFlow(r),
              })
            }}
          >
            一键发布
          </Button>
          <Button type="link" size="small" onClick={() => tryPublish(r)}>
            {t('designer.publish')}
          </Button>
          <Button type="link" size="small" onClick={() => runQuick(r)}>
            {t('rules.run')}
          </Button>
        </>
      ),
    },
  ]

  if (!workspaceId) return null

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
        <h2 style={{ margin: 0, fontFamily: "'Fraunces', Georgia, serif" }}>{t('rules.title')}</h2>
        <Button type="primary" onClick={() => setOpen(true)}>
          {t('rules.create')}
        </Button>
      </div>
      <Table rowKey="id" loading={loading} columns={columns} dataSource={data} pagination={false} />
      <Modal open={open} onCancel={() => setOpen(false)} title={t('rules.create')} footer={null} destroyOnClose>
        <Form form={f} layout="vertical" onFinish={onCreate}>
          <Form.Item name="name" label={t('rules.name')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="type" label={t('rules.type')} initialValue="document_review" rules={[{ required: true }]}>
            <Select options={RULE_TYPES} />
          </Form.Item>
          <Button type="primary" htmlType="submit" block>
            {t('rules.create')}
          </Button>
        </Form>
      </Modal>
    </div>
  )
}
