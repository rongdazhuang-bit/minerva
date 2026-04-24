import {
  ClockCircleOutlined,
  FileDoneOutlined,
  FileTextOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { Card, Col, Row, Statistic, Typography } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import './OverviewPage.css'

const { Title, Paragraph, Text } = Typography

/** 概览页演示用统计种子；后续可对接真实 API。 */
const SEED_STATS = {
  todayReview: 12,
  pending: 3,
  ruleHits: 1842,
  weeklyDocs: 96,
}

type ActivityItem = { id: string; label: string; time: string }

export function OverviewPage() {
  const { t } = useTranslation()
  const [updatedAt, setUpdatedAt] = useState<string | null>(null)
  const stats = SEED_STATS

  const activities: ActivityItem[] = useMemo(
    () => [
      { id: '1', label: t('overview.activity1'), time: t('overview.activityTime1') },
      { id: '2', label: t('overview.activity2'), time: t('overview.activityTime2') },
      { id: '3', label: t('overview.activity3'), time: t('overview.activityTime3') },
    ],
    [t],
  )

  useEffect(() => {
    setUpdatedAt(
      new Date().toLocaleString(undefined, {
        hour: '2-digit',
        minute: '2-digit',
        month: 'short',
        day: 'numeric',
      }),
    )
  }, [])

  return (
    <div className="minerva-overview">
      <div className="minerva-overview__hero">
        <Title level={3} className="minerva-overview__title">
          {t('home.title')}
        </Title>
        <Paragraph className="minerva-overview__subtitle">{t('home.subtitle')}</Paragraph>
        {updatedAt ? (
          <Text type="secondary" className="minerva-overview__meta">
            {t('overview.refreshedAt', { time: updatedAt })}
          </Text>
        ) : null}
      </div>

      <Row gutter={[16, 16]} className="minerva-overview__stats">
        <Col xs={24} sm={12} lg={6}>
          <Card size="small" className="minerva-overview__card" variant="borderless">
            <Statistic
              title={t('overview.stat.todayReview')}
              value={stats.todayReview}
              prefix={<FileDoneOutlined className="minerva-overview__icon" aria-hidden />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card size="small" className="minerva-overview__card" variant="borderless">
            <Statistic
              title={t('overview.stat.pending')}
              value={stats.pending}
              styles={{ content: { color: 'var(--minerva-link, #38bdf8)' } }}
              prefix={<ClockCircleOutlined className="minerva-overview__icon" aria-hidden />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card size="small" className="minerva-overview__card" variant="borderless">
            <Statistic
              title={t('overview.stat.ruleHits')}
              value={stats.ruleHits}
              prefix={<ThunderboltOutlined className="minerva-overview__icon" aria-hidden />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card size="small" className="minerva-overview__card" variant="borderless">
            <Statistic
              title={t('overview.stat.weeklyDocs')}
              value={stats.weeklyDocs}
              prefix={<FileTextOutlined className="minerva-overview__icon" aria-hidden />}
            />
          </Card>
        </Col>
      </Row>

      <Card
        size="small"
        title={t('overview.recentTitle')}
        className="minerva-overview__card minerva-overview__activity"
        variant="borderless"
      >
        <ul className="minerva-overview__activity-list">
          {activities.map((item) => (
            <li key={item.id} className="minerva-overview__list-item">
              <span>{item.label}</span>
              <Text type="secondary">{item.time}</Text>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  )
}
