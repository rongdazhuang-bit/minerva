import { Empty } from 'antd'
import { useTranslation } from 'react-i18next'

export function MenuConfigPage() {
  const { t } = useTranslation()
  return <Empty description={t('placeholders.menuConfig')} style={{ color: 'var(--minerva-ink)' }} />
}
