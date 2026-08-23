import { Typography } from 'antd'
import { useTranslation } from 'react-i18next'

/** Placeholder community / topic summaries page under a graph section. */
export function GraphKbSummariesPage() {
  const { t } = useTranslation()
  return (
    <div className="minerva-page-fill">
      <Typography.Title level={4}>{t('graphKb.page.summaries')}</Typography.Title>
    </div>
  )
}
