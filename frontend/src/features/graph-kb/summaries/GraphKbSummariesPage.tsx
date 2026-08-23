/** Placeholder community / topic summaries page under a graph section. */
import { Typography } from 'antd'
import { useTranslation } from 'react-i18next'

/** Placeholder community / topic summaries page (filled in Task 14). */
export function GraphKbSummariesPage() {
  const { t } = useTranslation()
  return (
    <div className="minerva-graph-kb-placeholder">
      <Typography.Title level={4}>{t('graphKb.page.summaries')}</Typography.Title>
    </div>
  )
}
