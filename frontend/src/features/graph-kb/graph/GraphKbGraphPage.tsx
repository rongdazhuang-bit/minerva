/** Placeholder graph canvas / table page under a graph section. */
import { Typography } from 'antd'
import { useTranslation } from 'react-i18next'

/** Placeholder graph canvas / table page (filled in Task 14). */
export function GraphKbGraphPage() {
  const { t } = useTranslation()
  return (
    <div className="minerva-graph-kb-placeholder">
      <Typography.Title level={4}>{t('graphKb.page.graph')}</Typography.Title>
    </div>
  )
}
