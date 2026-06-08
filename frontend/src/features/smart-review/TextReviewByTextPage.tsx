import { Empty } from 'antd'
import { useTranslation } from 'react-i18next'

/** 智能校审 · 文字校核 · 以文审文占位页。 */
export function TextReviewByTextPage() {
  const { t } = useTranslation()
  return (
    <Empty description={t('placeholders.textReviewByText')} style={{ color: 'var(--minerva-ink)' }} />
  )
}
