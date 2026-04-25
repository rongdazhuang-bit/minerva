import { Empty } from 'antd'
import { useTranslation } from 'react-i18next'

export function RolesPage() {
  const { t } = useTranslation()
  return <Empty description={t('placeholders.roleMgmt')} style={{ color: 'var(--minerva-ink)' }} />
}
