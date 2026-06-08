import { Empty } from 'antd'
import { useTranslation } from 'react-i18next'

/** 智能校审 · 图纸校审占位页。 */
export function DrawingReviewPage() {
  const { t } = useTranslation()
  return (
    <Empty description={t('placeholders.drawingReview')} style={{ color: 'var(--minerva-ink)' }} />
  )
}
