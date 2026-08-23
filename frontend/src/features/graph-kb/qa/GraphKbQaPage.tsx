/** Placeholder in-menu Q&A page under a graph section. */
import { Typography } from 'antd'
import { useTranslation } from 'react-i18next'

/** Placeholder in-menu Q&A page (filled in Task 14). */
export function GraphKbQaPage() {
  const { t } = useTranslation()
  return (
    <div className="minerva-graph-kb-placeholder">
      <Typography.Title level={4}>{t('graphKb.page.qa')}</Typography.Title>
    </div>
  )
}
