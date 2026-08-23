import { Typography } from 'antd'
import { useTranslation } from 'react-i18next'

/** Placeholder list page for `/app/graph-kb` (filled in a later task). */
export function GraphKbListPage() {
  const { t } = useTranslation()
  return (
    <div className="minerva-page-fill">
      <Typography.Title level={4}>{t('graphKb.page.list')}</Typography.Title>
    </div>
  )
}
