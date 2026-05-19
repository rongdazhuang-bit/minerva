/** Placeholder route for agent skill management until CRUD UI ships. */
import { Empty } from 'antd'
import { useTranslation } from 'react-i18next'

/** Renders the agent skills shell; replace with skill registry UI when APIs exist. */
export function AgentSkillsPage() {
  const { t } = useTranslation()
  return <Empty description={t('placeholders.agentsSkills')} style={{ color: 'var(--minerva-ink)' }} />
}
