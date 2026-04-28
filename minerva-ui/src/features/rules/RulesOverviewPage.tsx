import { Alert, Card, Col, Empty, List, Row, Spin, Statistic, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError } from '@/api/client'
import { getRuleBaseOverviewStats } from '@/api/ruleBase'
import { useAuth } from '@/app/AuthContext'
import { useDictItemTree } from '@/hooks/useDictItemTree'
import {
  ENG_SUBJECT_DOC_DICT_CODE,
  buildCodeNameMap,
} from '@/features/rules/scopeTriple'

function labelForCode(code: string, nameByCode: Map<string, string>) {
  const name = nameByCode.get(code)
  return name ? `${name} (${code})` : code
}

export function RulesOverviewPage() {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()

  const statsQuery = useQuery({
    queryKey: ['ruleBaseOverviewStats', workspaceId],
    queryFn: () => getRuleBaseOverviewStats(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const dictQuery = useDictItemTree(ENG_SUBJECT_DOC_DICT_CODE)

  const nameByCode = useMemo(
    () => buildCodeNameMap(dictQuery.data?.flat ?? []),
    [dictQuery.data?.flat],
  )

  const pending = statsQuery.isPending || dictQuery.isPending

  const err =
    statsQuery.error != null
      ? statsQuery.error
      : dictQuery.error != null
        ? dictQuery.error
        : null

  const stats = statsQuery.data

  return (
    <div
      className="rules-overview"
      style={{ padding: 0, maxWidth: 1100, color: 'var(--minerva-ink)' }}
    >
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
          <>
            <Row gutter={[16, 16]}>
              <Col xs={24} sm={12} lg={6}>
                <Card size="small" variant="borderless">
                  <Statistic
                    title={t('rules.overview.kpiEngineering')}
                    value={stats.engineering_codes.length}
                  />
                </Card>
              </Col>
              <Col xs={24} sm={12} lg={6}>
                <Card size="small" variant="borderless">
                  <Statistic
                    title={t('rules.overview.kpiSubject')}
                    value={stats.subject_codes.length}
                  />
                </Card>
              </Col>
              <Col xs={24} sm={12} lg={6}>
                <Card size="small" variant="borderless">
                  <Statistic
                    title={t('rules.overview.kpiDocType')}
                    value={stats.document_type_codes.length}
                  />
                </Card>
              </Col>
              <Col xs={24} sm={12} lg={6}>
                <Card size="small" variant="borderless">
                  <Statistic
                    title={t('rules.overview.kpiRules')}
                    value={stats.rule_count}
                  />
                </Card>
              </Col>
            </Row>

            <Typography.Title level={5} style={{ marginTop: 24, marginBottom: 8 }}>
              {t('rules.overview.sectionBreakdown')}
            </Typography.Title>

            <Row gutter={[16, 16]}>
              <Col xs={24} md={8}>
                <Card size="small" title={t('rules.overview.listEngineering')}>
                  <ScopeCodeList
                    codes={stats.engineering_codes}
                    nameByCode={nameByCode}
                    emptyText={t('rules.overview.emptyCodes')}
                  />
                </Card>
              </Col>
              <Col xs={24} md={8}>
                <Card size="small" title={t('rules.overview.listSubject')}>
                  <ScopeCodeList
                    codes={stats.subject_codes}
                    nameByCode={nameByCode}
                    emptyText={t('rules.overview.emptyCodes')}
                  />
                </Card>
              </Col>
              <Col xs={24} md={8}>
                <Card size="small" title={t('rules.overview.listDocType')}>
                  <ScopeCodeList
                    codes={stats.document_type_codes}
                    nameByCode={nameByCode}
                    emptyText={t('rules.overview.emptyCodes')}
                  />
                </Card>
              </Col>
            </Row>
          </>
        )}

      </Spin>
    </div>
  )
}

function ScopeCodeList({
  codes,
  nameByCode,
  emptyText,
}: {
  codes: string[]
  nameByCode: Map<string, string>
  emptyText: string
}) {
  if (codes.length === 0) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyText} />
  }
  return (
    <List
      size="small"
      dataSource={codes}
      renderItem={(code) => (
        <List.Item>
          <span title={code}>{labelForCode(code, nameByCode)}</span>
        </List.Item>
      )}
    />
  )
}
