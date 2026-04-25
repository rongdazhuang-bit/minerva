import { Empty } from 'antd'
import { useTranslation } from 'react-i18next'

export function RulesFileOcrPage() {
  const { t } = useTranslation()
  return <Empty description={t('placeholders.rulesFileOcr')} style={{ color: 'var(--minerva-ink)' }} />
}
