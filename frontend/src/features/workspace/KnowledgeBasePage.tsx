/** Placeholder route for workspace knowledge base until ingestion and search UI ship. */
import { Empty } from 'antd'
import { useTranslation } from 'react-i18next'

/** Renders the knowledge base shell; replace with corpus management when APIs exist. */
export function KnowledgeBasePage() {
  const { t } = useTranslation()
  return <Empty description={t('placeholders.knowledgeBase')} style={{ color: 'var(--minerva-ink)' }} />
}
