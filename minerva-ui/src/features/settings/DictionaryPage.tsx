import { Empty } from 'antd'
import { useTranslation } from 'react-i18next'

export function DictionaryPage() {
  const { t } = useTranslation()
  return <Empty description={t('placeholders.dictionary')} style={{ color: 'var(--minerva-ink)' }} />
}
