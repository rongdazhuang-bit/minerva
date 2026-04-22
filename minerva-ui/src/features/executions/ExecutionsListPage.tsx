import { listExecutions } from '@/api/executions'
import { ApiError } from '@/api/client'
import type { ExecutionListItem } from '@/api/types'
import { useAuth } from '@/app/AuthContext'
import { Button, Table, Tag, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

function colorForStatus(s: string) {
  if (s === 'succeeded') return 'success'
  if (s === 'failed' || s === 'step_limit') return 'error'
  if (s === 'running') return 'processing'
  return 'default'
}

export function ExecutionsListPage() {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const nav = useNavigate()
  const [data, setData] = useState<ExecutionListItem[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    if (!workspaceId) return
    setLoading(true)
    try {
      setData(await listExecutions(workspaceId))
    } catch (e) {
      if (e instanceof ApiError) void message.error(e.message)
    } finally {
      setLoading(false)
    }
  }, [workspaceId])

  useEffect(() => {
    void load()
  }, [load])

  const columns: ColumnsType<ExecutionListItem> = [
    {
      title: t('executions.id'),
      dataIndex: 'id',
      key: 'id',
      render: (id: string) => <code style={{ fontSize: 12 }}>{id.slice(0, 8)}…</code>,
    },
    { title: t('executions.status'), dataIndex: 'status', key: 'status', width: 120, render: (s) => <Tag color={colorForStatus(s)}>{s}</Tag> },
    { title: t('executions.steps'), dataIndex: 'step_count', key: 'step_count', width: 90 },
    {
      title: t('executions.time'),
      dataIndex: 'created_at',
      key: 'created_at',
      render: (d: string) => new Date(d).toLocaleString(),
    },
    {
      title: ' ',
      key: 'a',
      width: 100,
      render: (_, r) => (
        <Button type="link" size="small" onClick={() => void nav(`/app/executions/${r.id}`)}>
          {t('executions.view')}
        </Button>
      ),
    },
  ]

  if (!workspaceId) return null

  return (
    <div>
      <h2 style={{ fontFamily: "'Fraunces', Georgia, serif" }}>{t('executions.title')}</h2>
      <Table rowKey="id" loading={loading} columns={columns} dataSource={data} />
    </div>
  )
}
