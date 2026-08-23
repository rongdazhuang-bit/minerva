import { Typography } from 'antd'
import { useTranslation } from 'react-i18next'

/** Placeholder documents page under a graph section. */
export function GraphKbDocumentsPage() {
  const { t } = useTranslation()
  return (
    <div className="minerva-page-fill">
      <Typography.Title level={4}>{t('graphKb.page.documents')}</Typography.Title>
    </div>
  )
}
