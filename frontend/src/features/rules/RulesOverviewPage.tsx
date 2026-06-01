import {
  FileTextOutlined,
  ProjectOutlined,
  TagsOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons'
import { Alert, Card, Col, Row, Spin, Statistic } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ApiError } from '@/api/client'
import { getRuleBaseOverviewStats } from '@/api/ruleBase'
import { useAuth } from '@/app/AuthContext'
import { useCountUp } from '@/hooks/useCountUp'
import './RulesOverviewPage.css'

export function RulesOverviewPage() {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()

  const statsQuery = useQuery({
    queryKey: ['ruleBaseOverviewStats', workspaceId],
    queryFn: () => getRuleBaseOverviewStats(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const pending = statsQuery.isPending
  const err = statsQuery.error
  const stats = statsQuery.data

  const hasStats = Boolean(stats)
  const targetEng = stats?.engineering_codes.length ?? 0
  const targetSub = stats?.subject_codes.length ?? 0
  const targetDoc = stats?.document_type_codes.length ?? 0
  const targetRules = stats?.rule_count ?? 0

  const displayEng = useCountUp(targetEng, { enabled: hasStats })
  const displaySub = useCountUp(targetSub, { enabled: hasStats })
  const displayDoc = useCountUp(targetDoc, { enabled: hasStats })
  const displayRules = useCountUp(targetRules, { enabled: hasStats })

  return (
    <div className="minerva-rules-overview">
      {err != null && (
        <Alert
          type="error"
          showIcon
          message={
            err instanceof ApiError ? err.message : t('common.error')
          }
          style={{ marginBottom: 16 }}
        />
      )}

      <Spin spinning={pending}>
        {stats != null && (
          <div className="minerva-rules-overview__stats-scroll">
            <Row wrap={false} gutter={[18, 0]} className="minerva-rules-overview__stats">
              <Col flex="1 1 0" className="minerva-rules-overview__stat-col">
                <Card
                  size="small"
                  className="minerva-rules-overview__card minerva-rules-overview__card--engineering"
                  variant="borderless"
                >
                  <Statistic
                    title={t('rules.overview.kpiEngineering')}
                    value={displayEng}
                    prefix={
                      <ProjectOutlined
                        className="minerva-rules-overview__icon"
                        aria-hidden
                      />
                    }
                  />
                </Card>
              </Col>
              <Col flex="1 1 0" className="minerva-rules-overview__stat-col">
                <Card
                  size="small"
                  className="minerva-rules-overview__card minerva-rules-overview__card--subject"
                  variant="borderless"
                >
                  <Statistic
                    title={t('rules.overview.kpiSubject')}
                    value={displaySub}
                    prefix={
                      <TagsOutlined
                        className="minerva-rules-overview__icon"
                        aria-hidden
                      />
                    }
                  />
                </Card>
              </Col>
              <Col flex="1 1 0" className="minerva-rules-overview__stat-col">
                <Card
                  size="small"
                  className="minerva-rules-overview__card minerva-rules-overview__card--document"
                  variant="borderless"
                >
                  <Statistic
                    title={t('rules.overview.kpiDocType')}
                    value={displayDoc}
                    prefix={
                      <FileTextOutlined
                        className="minerva-rules-overview__icon"
                        aria-hidden
                      />
                    }
                  />
                </Card>
              </Col>
              <Col flex="1 1 0" className="minerva-rules-overview__stat-col">
                <Card
                  size="small"
                  className="minerva-rules-overview__card minerva-rules-overview__card--rules"
                  variant="borderless"
                >
                  <Statistic
                    title={t('rules.overview.kpiRules')}
                    value={displayRules}
                    prefix={
                      <UnorderedListOutlined
                        className="minerva-rules-overview__icon"
                        aria-hidden
                      />
                    }
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
