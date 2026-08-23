import { Typography } from 'antd'
import { useTranslation } from 'react-i18next'

/** Placeholder in-menu Q&A page under a graph section. */
export function GraphKbQaPage() {
  const { t } = useTranslation()
  return (
    <div className="minerva-page-fill">
      <Typography.Title level={4}>{t('graphKb.page.qa')}</Typography.Title>
    </div>
  )
}
