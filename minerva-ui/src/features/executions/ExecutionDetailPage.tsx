import { getExecution } from '@/api/executions'
import { ApiError } from '@/api/client'
import type { ExecutionDetail } from '@/api/types'
import { useAuth } from '@/app/AuthContext'
import { Breadcrumb, Descriptions, Tag, Timeline, message } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'

function colorForStatus(s: string) {
  if (s === 'succeeded') return 'success'
  if (s === 'failed' || s === 'step_limit') return 'error'
  if (s === 'running') return 'processing'
  return 'default'
}

export function ExecutionDetailPage() {
  const { executionId = '' } = useParams()
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const [row, setRow] = useState<ExecutionDetail | null>(null)

  const load = useCallback(async () => {
    if (!workspaceId || !executionId) return
    try {
      setRow(await getExecution(workspaceId, executionId))
    } catch (e) {
      if (e instanceof ApiError) void message.error(e.message)
    }
  }, [executionId, workspaceId])

  useEffect(() => {
    void load()
  }, [load])

  if (!workspaceId) return null
  if (!row) return null

  return (
    <div>
      <Breadcrumb
        style={{ marginBottom: 12 }}
        items={[
          { title: <Link to="/app/executions">{t('nav.executions')}</Link> },
          { title: row.id },
        ]}
      />
      <Descriptions bordered column={1} size="small" style={{ marginBottom: 16 }}>
        <Descriptions.Item label="id">
          <code>{row.id}</code>
        </Descriptions.Item>
        <Descriptions.Item label={t('executions.status')}>
          <Tag color={colorForStatus(row.status)}>{row.status}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label={t('executions.steps')}>{row.step_count}</Descriptions.Item>
        <Descriptions.Item label="当前节点">{row.current_node_id ?? '—'}</Descriptions.Item>
        <Descriptions.Item label="error">{row.error_code ?? '—'}</Descriptions.Item>
        <Descriptions.Item label="detail">
          {row.error_detail ?? '—'}
        </Descriptions.Item>
        <Descriptions.Item label="input">
          <pre style={{ fontSize: 12, maxHeight: 200, overflow: 'auto' }}>
            {JSON.stringify(row.input_json, null, 2)}
          </pre>
        </Descriptions.Item>
      </Descriptions>
      <h3>事件</h3>
      <Timeline
        items={row.events.map((e) => ({
          key: e.id,
          color: e.event_type === 'finished' ? 'green' : 'blue',
          children: (
            <div>
              <div>
                <Tag>{e.event_type}</Tag> {new Date(e.created_at).toLocaleString()}
              </div>
              <pre style={{ fontSize: 12, marginTop: 4, whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(e.payload, null, 2)}
              </pre>
            </div>
          ),
        }))}
      />
    </div>
  )
}
