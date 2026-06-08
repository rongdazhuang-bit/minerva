import { Empty } from 'antd'
import { useTranslation } from 'react-i18next'

/** 智能校审 · 文字校核占位页。 */
export function TextProofreadingPage() {
  const { t } = useTranslation()
  return (
    <Empty
      description={t('placeholders.textProofreading')}
      style={{ color: 'var(--minerva-ink)' }}
    />
  )
}
