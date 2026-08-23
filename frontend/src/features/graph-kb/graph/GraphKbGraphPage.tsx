import { Typography } from 'antd'
import { useTranslation } from 'react-i18next'

/** Placeholder graph canvas / table page under a graph section. */
export function GraphKbGraphPage() {
  const { t } = useTranslation()
  return (
    <div className="minerva-page-fill">
      <Typography.Title level={4}>{t('graphKb.page.graph')}</Typography.Title>
    </div>
  )
}
