import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
} from '@ant-design/icons'
import { Alert, Card, Col, Empty, Row, Spin, Statistic } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ApiError } from '@/api/client'
import { getOcrFileOverviewStats } from '@/api/ocrFile'
import { useAuth } from '@/app/AuthContext'
import { useCountUp } from '@/hooks/useCountUp'
import './RulesFileOcrPage.css'

export function RulesFileOcrPage() {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const statsQuery = useQuery({
    queryKey: ['ocrFileOverviewStats', workspaceId],
    queryFn: () => getOcrFileOverviewStats(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const pending = statsQuery.isPending
  const err = statsQuery.error
  const stats = statsQuery.data

  const hasStats = Boolean(stats)
  const displayInit = useCountUp(stats?.init_count ?? 0, { enabled: hasStats })
  const displayProcess = useCountUp(stats?.process_count ?? 0, { enabled: hasStats })
  const displaySuccess = useCountUp(stats?.success_count ?? 0, { enabled: hasStats })
  const displayFailed = useCountUp(stats?.failed_count ?? 0, { enabled: hasStats })

  return (
    <div className="minerva-file-ocr-overview">
      {err != null && (
        <Alert
          type="error"
          showIcon
          message={err instanceof ApiError ? err.message : t('common.error')}
          style={{ marginBottom: 16 }}
        />
      )}
      <Spin spinning={pending}>
        {stats == null ? (
          <Empty description={t('placeholders.rulesFileOcr')} style={{ color: 'var(--minerva-ink)' }} />
        ) : (
          <div className="minerva-file-ocr-overview__stats-scroll">
            <Row wrap={false} gutter={[18, 0]} className="minerva-file-ocr-overview__stats">
              <Col flex="1 1 0" className="minerva-file-ocr-overview__stat-col">
                <Card
                  size="small"
                  className="minerva-file-ocr-overview__card minerva-file-ocr-overview__card--init"
                  variant="borderless"
                >
                  <Statistic
                    title={t('fileOcr.overview.kpiInit')}
                    value={displayInit}
                    prefix={<ClockCircleOutlined className="minerva-file-ocr-overview__icon" aria-hidden />}
                  />
                </Card>
              </Col>
              <Col flex="1 1 0" className="minerva-file-ocr-overview__stat-col">
                <Card
                  size="small"
                  className="minerva-file-ocr-overview__card minerva-file-ocr-overview__card--process"
                  variant="borderless"
                >
                  <Statistic
                    title={t('fileOcr.overview.kpiProcess')}
                    value={displayProcess}
                    prefix={<LoadingOutlined className="minerva-file-ocr-overview__icon" aria-hidden />}
                  />
                </Card>
              </Col>
              <Col flex="1 1 0" className="minerva-file-ocr-overview__stat-col">
                <Card
                  size="small"
                  className="minerva-file-ocr-overview__card minerva-file-ocr-overview__card--success"
                  variant="borderless"
                >
                  <Statistic
                    title={t('fileOcr.overview.kpiSuccess')}
                    value={displaySuccess}
                    prefix={<CheckCircleOutlined className="minerva-file-ocr-overview__icon" aria-hidden />}
                  />
                </Card>
              </Col>
              <Col flex="1 1 0" className="minerva-file-ocr-overview__stat-col">
                <Card
                  size="small"
                  className="minerva-file-ocr-overview__card minerva-file-ocr-overview__card--failed"
                  variant="borderless"
                >
                  <Statistic
                    title={t('fileOcr.overview.kpiFailed')}
                    value={displayFailed}
                    prefix={<CloseCircleOutlined className="minerva-file-ocr-overview__icon" aria-hidden />}
                  />
                </Card>
              </Col>
            </Row>
          </div>
        )}
      </Spin>
    </div>
  )
}

export function RulesFileOcrTasksPage() {
  const { t } = useTranslation()
  return <Empty description={t('placeholders.rulesFileOcrTasks')} style={{ color: 'var(--minerva-ink)' }} />
}
