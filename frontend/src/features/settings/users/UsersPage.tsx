import { Empty } from 'antd'
import { useTranslation } from 'react-i18next'

export function UsersPage() {
  const { t } = useTranslation()
  return <Empty description={t('placeholders.userMgmt')} style={{ color: 'var(--minerva-ink)' }} />
}
