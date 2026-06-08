/** Hit testing page for one knowledge base. */

import { useMutation, useQuery } from '@tanstack/react-query'

import { Button, Card, Form, Input, List, Space, Typography, message } from 'antd'

import { useState } from 'react'

import { useTranslation } from 'react-i18next'

import { useParams } from 'react-router-dom'

import { useAuth } from '@/app/AuthContext'

import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'

import { listDatasetQueries, runHitTesting, type HitTestingRecord } from '@/features/dataset/api/hitTesting'



/** Recall test page for one knowledge base. */

export function HitTestingPage() {

  const { t } = useTranslation()

  const { workspaceId } = useAuth()

  const { datasetId = '' } = useParams()

  const [form] = Form.useForm<{ query: string }>()

  const [records, setRecords] = useState<HitTestingRecord[]>([])



  const historyQ = useQuery({

    queryKey: ['dataset-queries', workspaceId, datasetId],

    queryFn: () => listDatasetQueries(workspaceId!, datasetId, { page: 1, page_size: DEFAULT_PAGE_SIZE }),

    enabled: Boolean(workspaceId && datasetId),

  })



  const testM = useMutation({

    mutationFn: (query: string) => runHitTesting(workspaceId!, datasetId, { query }),

    onSuccess: (data) => {

      setRecords(data.records)

      void historyQ.refetch()

    },

    onError: (err: Error) => message.error(err.message),

  })



  const renderSegmentBody = (segment: HitTestingRecord['segment']) => (

    <Space direction="vertical" size={4} style={{ width: '100%' }}>

      <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>

        {segment.content}

      </Typography.Paragraph>

      {segment.child_content ? (

        <Typography.Paragraph type="secondary" style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>

          {t('dataset.hitTesting.childMatch')}: {segment.child_content}

        </Typography.Paragraph>

      ) : null}

      {segment.answer ? (

        <Typography.Paragraph type="secondary" style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>

          {t('dataset.segments.column.answer')}: {segment.answer}

        </Typography.Paragraph>

      ) : null}

    </Space>

  )



  return (

    <Space direction="vertical" size="large" style={{ width: '100%' }}>

      <Card title={t('dataset.hitTesting.title')}>

        <Form

          form={form}

          layout="vertical"

          onFinish={(values) => testM.mutate(values.query.trim())}

        >

          <Form.Item

            name="query"

            label={t('dataset.hitTesting.query')}

            rules={[{ required: true, message: t('dataset.hitTesting.queryRequired') }]}

          >

            <Input.TextArea allowClear rows={3} placeholder={t('dataset.hitTesting.queryPh')} />

          </Form.Item>

          <Button type="primary" htmlType="submit" loading={testM.isPending}>

            {t('dataset.hitTesting.run')}

          </Button>

        </Form>

      </Card>



      <Card title={t('dataset.hitTesting.results')}>

        {records.length === 0 ? (

          <Typography.Text type="secondary">{t('dataset.hitTesting.empty')}</Typography.Text>

        ) : (

          <List

            dataSource={records}

            renderItem={(item, index) => (

              <List.Item>

                <List.Item.Meta

                  title={`#${index + 1} · ${item.document.name} · ${item.score.toFixed(4)}`}

                  description={renderSegmentBody(item.segment)}

                />

              </List.Item>

            )}

          />

        )}

      </Card>



      <Card title={t('dataset.hitTesting.history')}>

        <List

          loading={historyQ.isLoading}

          dataSource={historyQ.data?.items ?? []}

          locale={{ emptyText: t('dataset.hitTesting.historyEmpty') }}

          renderItem={(item) => (

            <List.Item>

              <List.Item.Meta

                title={item.content}

                description={item.create_at ? new Date(item.create_at).toLocaleString() : '—'}

              />

            </List.Item>

          )}

        />

      </Card>

    </Space>

  )

}

