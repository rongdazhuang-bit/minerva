import { Empty } from 'antd'
import { useTranslation } from 'react-i18next'

export function ModelProvidersPage() {
  const { t } = useTranslation()
  return <Empty description={t('placeholders.modelProviders')} style={{ color: 'var(--minerva-ink)' }} />
}
