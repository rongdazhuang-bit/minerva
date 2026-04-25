import { Empty } from 'antd'
import { useTranslation } from 'react-i18next'

export function DataSourcesPage() {
  const { t } = useTranslation()
  return <Empty description={t('placeholders.dataSources')} style={{ color: 'var(--minerva-ink)' }} />
}
