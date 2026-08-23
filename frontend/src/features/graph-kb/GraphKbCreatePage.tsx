import { Typography } from 'antd'
import { useTranslation } from 'react-i18next'

/** Placeholder create page for `/app/graph-kb/create` (filled in a later task). */
export function GraphKbCreatePage() {
  const { t } = useTranslation()
  return (
    <div className="minerva-page-fill">
      <Typography.Title level={4}>{t('graphKb.page.create')}</Typography.Title>
    </div>
  )
}
