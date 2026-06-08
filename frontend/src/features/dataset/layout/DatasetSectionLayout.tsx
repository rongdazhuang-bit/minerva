/** Detail layout with tabs for documents, hit testing, and settings. */
import { useQuery } from '@tanstack/react-query'
import { Card, Spin, Tabs, Typography } from 'antd'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '@/app/AuthContext'
import { getDataset } from '@/features/dataset/api/documents'

/** Shell for `/app/dataset/:datasetId/*` sub-routes. */
export function DatasetSectionLayout() {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const { datasetId = '' } = useParams()
  const navigate = useNavigate()
  const location = useLocation()

  const detailQ = useQuery({
    queryKey: ['dataset-detail', workspaceId, datasetId],
    queryFn: () => getDataset(workspaceId!, datasetId),
    enabled: Boolean(workspaceId && datasetId),
  })

  const activeKey = useMemo(() => {
    if (location.pathname.includes('/hit-testing')) return 'hit-testing'
    if (location.pathname.includes('/settings')) return 'settings'
    return 'documents'
  }, [location.pathname])

  const tabItems = useMemo(
    () => [
      {
        key: 'documents',
        label: t('dataset.tabs.documents'),
      },
      {
        key: 'hit-testing',
        label: t('dataset.tabs.hitTesting'),
      },
      {
        key: 'settings',
        label: t('dataset.tabs.settings'),
      },
    ],
    [t],
  )

  if (!datasetId) {
    return null
  }

  return (
    <Spin spinning={detailQ.isLoading}>
      <Card style={{ marginBottom: 16 }}>
        <Typography.Title level={4} style={{ marginBottom: 4 }}>
          {detailQ.data?.name ?? t('dataset.detail.placeholder')}
        </Typography.Title>
        {detailQ.data?.description ? (
          <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
            {detailQ.data.description}
          </Typography.Paragraph>
        ) : null}
        {detailQ.data?.chunk_structure && detailQ.data.chunk_structure !== 'text_model' ? (
          <Typography.Text type="secondary">
            {t(
              (
                {
                  text_model: 'dataset.create.docForm.text',
                  hierarchical_model: 'dataset.create.docForm.hierarchical',
                  qa_model: 'dataset.create.docForm.qa',
                } as const
              )[detailQ.data.chunk_structure as 'text_model' | 'hierarchical_model' | 'qa_model'] ??
                'dataset.create.docForm.text',
            )}
          </Typography.Text>
        ) : null}
      </Card>
      <Tabs
        activeKey={activeKey}
        items={tabItems}
        onChange={(key) => {
          navigate(`/app/dataset/${datasetId}/${key === 'documents' ? 'documents' : key}`)
        }}
      />
      <Outlet />
    </Spin>
  )
}
