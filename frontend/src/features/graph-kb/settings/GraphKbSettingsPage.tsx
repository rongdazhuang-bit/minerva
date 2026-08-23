import { Typography } from 'antd'
import { useTranslation } from 'react-i18next'

/** Placeholder settings page under a graph section. */
export function GraphKbSettingsPage() {
  const { t } = useTranslation()
  return (
    <div className="minerva-page-fill">
      <Typography.Title level={4}>{t('graphKb.page.settings')}</Typography.Title>
    </div>
  )
}
