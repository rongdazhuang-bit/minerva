/** Detail layout with tabs for documents, hit testing, and settings. */
import { Tabs } from 'antd'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'
import './DatasetSectionLayout.css'

/** Shell for `/app/dataset/:datasetId/*` sub-routes. */
export function DatasetSectionLayout() {
  const { t } = useTranslation()
  const { datasetId = '' } = useParams()
  const navigate = useNavigate()
  const location = useLocation()

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
    <div className="minerva-dataset-section-layout">
      <div className="minerva-dataset-section-layout__tabs">
        <Tabs
          activeKey={activeKey}
          items={tabItems}
          onChange={(key) => {
            navigate(`/app/dataset/${datasetId}/${key === 'documents' ? 'documents' : key}`)
          }}
        />
      </div>
      <div className="minerva-dataset-section-layout__body minerva-scrollbar-styled">
        <Outlet />
      </div>
    </div>
  )
}
