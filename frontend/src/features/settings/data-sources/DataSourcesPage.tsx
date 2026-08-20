import { Empty } from 'antd'
import { useTranslation } from 'react-i18next'

/** 系统设置 · 数据源占位页。 */
export function DataSourcesPage() {
  const { t } = useTranslation()
  return (
    <div className="minerva-page-fill">
      <Empty description={t('placeholders.dataSources')} style={{ color: 'var(--minerva-ink)' }} />
    </div>
  )
}
