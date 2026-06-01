import { Empty } from 'antd'
import { useTranslation } from 'react-i18next'

export function SmartReviewPage() {
  const { t } = useTranslation()
  return <Empty description={t('placeholders.smartReview')} style={{ color: 'var(--minerva-ink)' }} />
}
