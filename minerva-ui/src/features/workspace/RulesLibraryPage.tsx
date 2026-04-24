import { Empty } from 'antd'
import { useTranslation } from 'react-i18next'

export function RulesLibraryPage() {
  const { t } = useTranslation()
  return <Empty description={t('placeholders.rulesLibrary')} style={{ color: 'var(--minerva-ink)' }} />
}
