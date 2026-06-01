import {
  BookOutlined,
  FileSearchOutlined,
  ReadOutlined,
  RobotOutlined,
  ScanOutlined,
  TranslationOutlined,
} from '@ant-design/icons'
import { Alert, Card, Empty, Spin } from 'antd'
import { useQuery } from '@tanstack/react-query'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { ComponentType, ReactNode } from 'react'
import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '@/api/client'
import { getAgentOverviewUsageDailyStats } from '@/api/agent'
import { formatTokenCount } from '@/api/agent-stream-v2'
import {
  getOcrFileOverviewLogDailyStats,
  type OcrFileOverviewLogDailyStatItem,
} from '@/api/ocrTask'
import { getRuleBaseOverviewStats } from '@/api/ruleBase'
import { useAuth } from '@/app/AuthContext'
import './OverviewPage.css'

const OVERVIEW_CHART_DAYS = 7

const RULES_BAR_COLORS = ['#0ea5e9', '#8b5cf6', '#f59e0b', '#22c55e']

/** 快捷入口单项：路由、图标、渐变 modifier、i18n 键。 */
type OverviewAppItem = {
  key: string
  path: string
  icon: ComponentType<{ className?: string }>
  iconModifier:
    | 'agents'
    | 'translate'
    | 'knowledge-base'
    | 'smart-review'
    | 'rules'
    | 'file-ocr'
  titleKey: string
  descKey: string
}

/** 概览页 6 个快捷应用入口配置（顺序即展示顺序）。 */
const OVERVIEW_APPS: OverviewAppItem[] = [
  {
    key: 'agents',
    path: '/app/agents/chat',
    icon: RobotOutlined,
    iconModifier: 'agents',
    titleKey: 'overview.apps.agents',
    descKey: 'overview.apps.agentsDesc',
  },
  {
    key: 'translate',
    path: '/app/translate',
    icon: TranslationOutlined,
    iconModifier: 'translate',
    titleKey: 'overview.apps.translate',
    descKey: 'overview.apps.translateDesc',
  },
  {
    key: 'knowledge-base',
    path: '/app/knowledge-base',
    icon: ReadOutlined,
    iconModifier: 'knowledge-base',
    titleKey: 'overview.apps.knowledgeBase',
    descKey: 'overview.apps.knowledgeBaseDesc',
  },
  {
    key: 'smart-review',
    path: '/app/smart-review',
    icon: FileSearchOutlined,
    iconModifier: 'smart-review',
    titleKey: 'overview.apps.smartReview',
    descKey: 'overview.apps.smartReviewDesc',
  },
  {
    key: 'rules',
    path: '/app/rules/overview',
    icon: BookOutlined,
    iconModifier: 'rules',
    titleKey: 'overview.apps.rules',
    descKey: 'overview.apps.rulesDesc',
  },
  {
    key: 'file-ocr',
    path: '/app/file-ocr/overview',
    icon: ScanOutlined,
    iconModifier: 'file-ocr',
    titleKey: 'overview.apps.fileOcr',
    descKey: 'overview.apps.fileOcrDesc',
  },
]

type OverviewAppCardProps = {
  item: OverviewAppItem
  title: string
  description: string
  onOpen: (path: string) => void
}

/** 监听图表容器宽度，供 Recharts 使用。 */
function useChartBoxWidth(active: boolean) {
  const chartBoxRef = useRef<HTMLDivElement | null>(null)
  const [chartBoxW, setChartBoxW] = useState(0)

  useLayoutEffect(() => {
    if (!active) {
      setChartBoxW(0)
      return
    }
    const el = chartBoxRef.current
    if (el == null) return
    const measure = () => {
      const w = Math.floor(el.getBoundingClientRect().width)
      setChartBoxW(w > 0 ? w : 0)
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => {
      ro.disconnect()
    }
  }, [active])

  return { chartBoxRef, chartBoxW }
}

/** 概览图表卡片通用外壳。 */
function OverviewChartCard({
  title,
  pending,
  error,
  empty,
  hasData,
  children,
}: {
  title: string
  pending: boolean
  error: unknown
  empty: string
  hasData: boolean
  children: ReactNode
}) {
  const { t } = useTranslation()

  return (
    <Card size="small" variant="borderless" className="minerva-overview__chart-card" title={title}>
      {error != null && (
        <Alert
          type="warning"
          showIcon
          message={error instanceof ApiError ? error.message : t('common.error')}
          style={{ marginBottom: 12 }}
        />
      )}
      <Spin spinning={pending}>
        {!pending && error == null && hasData ? children : null}
        {!pending && error == null && !hasData ? (
          <Empty description={empty} style={{ color: 'var(--minerva-ink)' }} />
        ) : null}
      </Spin>
    </Card>
  )
}

/** Coerce OCR daily row fields so charts stay numeric. */
function normalizeOcrLogDailyChartRow(r: OcrFileOverviewLogDailyStatItem): {
  date: string
  paddle_success: number
  paddle_failed: number
  mineru_success: number
  mineru_failed: number
} {
  const n = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : 0)
  return {
    date: r.date,
    paddle_success: n(r.paddle_success),
    paddle_failed: n(r.paddle_failed),
    mineru_success: n(r.mineru_success),
    mineru_failed: n(r.mineru_failed),
  }
}

/** 单个快捷应用入口卡片（整卡可点击）。 */
function OverviewAppCard({ item, title, description, onOpen }: OverviewAppCardProps) {
  const Icon = item.icon

  return (
    <button
      type="button"
      className="minerva-overview__app-card"
      aria-label={title}
      onClick={() => onOpen(item.path)}
    >
      <span
        className={`minerva-overview__app-icon minerva-overview__app-icon--${item.iconModifier}`}
        aria-hidden
      >
        <Icon />
      </span>
      <span className="minerva-overview__app-body">
        <span className="minerva-overview__app-name">{title}</span>
        <span className="minerva-overview__app-desc">{description}</span>
      </span>
    </button>
  )
}

/** 智能体近 7 日 token 消耗折线图。 */
function AgentTokenUsageChart(): ReactNode {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()

  const dailyQuery = useQuery({
    queryKey: ['agentOverviewUsageDailyStats', workspaceId],
    queryFn: () => getAgentOverviewUsageDailyStats(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const chartData = useMemo(() => dailyQuery.data?.items ?? [], [dailyQuery.data?.items])
  const hasData = chartData.length > 0
  const { chartBoxRef, chartBoxW } = useChartBoxWidth(hasData)

  return (
    <OverviewChartCard
      title={t('overview.tokenChartTitle')}
      pending={dailyQuery.isPending}
      error={dailyQuery.error}
      empty={t('overview.tokenChartEmpty')}
      hasData={hasData}
    >
      <div ref={chartBoxRef} className="minerva-overview__chart-wrap">
        {chartBoxW > 0 ? (
          <LineChart
            width={chartBoxW}
            height={240}
            data={chartData}
            margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="var(--minerva-border, #2a3f58)" opacity={0.45} />
            <XAxis
              dataKey="date"
              tickFormatter={(v) => (typeof v === 'string' && v.length >= 10 ? v.slice(5) : String(v))}
              tick={{ fill: 'var(--minerva-ink-muted, #94a3b8)', fontSize: 10 }}
            />
            <YAxis
              width={40}
              tickFormatter={(v) => formatTokenCount(Number(v))}
              tick={{ fill: 'var(--minerva-ink-muted, #94a3b8)', fontSize: 10 }}
            />
            <RechartsTooltip
              contentStyle={{
                background: 'var(--minerva-surface, #1a2836)',
                borderColor: 'var(--minerva-border, #2a3f58)',
              }}
              formatter={(value) => formatTokenCount(Number(value ?? 0))}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Line
              type="monotone"
              dataKey="prompt_tokens"
              name={t('overview.seriesPromptTokens')}
              stroke="#6366f1"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="completion_tokens"
              name={t('overview.seriesCompletionTokens')}
              stroke="#22c55e"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="cached_tokens"
              name={t('overview.seriesCachedTokens')}
              stroke="#38bdf8"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="reasoning_tokens"
              name={t('overview.seriesReasoningTokens')}
              stroke="#f97316"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        ) : (
          <div className="minerva-overview__chart-measure" aria-hidden />
        )}
      </div>
    </OverviewChartCard>
  )
}

/** OCR 近 7 日任务执行折线图。 */
function OcrTaskDailyChart(): ReactNode {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()

  const dailyQuery = useQuery({
    queryKey: ['ocrFileOverviewLogDailyStats', workspaceId, OVERVIEW_CHART_DAYS],
    queryFn: () => getOcrFileOverviewLogDailyStats(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const chartData = useMemo(() => {
    const raw = dailyQuery.data?.items
    if (raw == null || raw.length === 0) return []
    return raw.slice(-OVERVIEW_CHART_DAYS).map((row) => normalizeOcrLogDailyChartRow(row))
  }, [dailyQuery.data?.items])

  const hasData = chartData.length > 0
  const { chartBoxRef, chartBoxW } = useChartBoxWidth(hasData)

  return (
    <OverviewChartCard
      title={t('overview.ocrChartTitle')}
      pending={dailyQuery.isPending}
      error={dailyQuery.error}
      empty={t('overview.ocrChartEmpty')}
      hasData={hasData}
    >
      <div ref={chartBoxRef} className="minerva-overview__chart-wrap">
        {chartBoxW > 0 ? (
          <LineChart
            width={chartBoxW}
            height={240}
            data={chartData}
            margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="var(--minerva-border, #2a3f58)" opacity={0.45} />
            <XAxis
              dataKey="date"
              tickFormatter={(v) => (typeof v === 'string' && v.length >= 10 ? v.slice(5) : String(v))}
              tick={{ fill: 'var(--minerva-ink-muted, #94a3b8)', fontSize: 10 }}
            />
            <YAxis
              width={36}
              allowDecimals={false}
              tick={{ fill: 'var(--minerva-ink-muted, #94a3b8)', fontSize: 10 }}
            />
            <RechartsTooltip
              contentStyle={{
                background: 'var(--minerva-surface, #1a2836)',
                borderColor: 'var(--minerva-border, #2a3f58)',
              }}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Line
              type="monotone"
              dataKey="paddle_success"
              name={t('fileOcr.overview.seriesPaddleSuccess')}
              stroke="#22c55e"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="paddle_failed"
              name={t('fileOcr.overview.seriesPaddleFailed')}
              stroke="#ef4444"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="mineru_success"
              name={t('fileOcr.overview.seriesMineruSuccess')}
              stroke="#38bdf8"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="mineru_failed"
              name={t('fileOcr.overview.seriesMineruFailed')}
              stroke="#f97316"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        ) : (
          <div className="minerva-overview__chart-measure" aria-hidden />
        )}
      </div>
    </OverviewChartCard>
  )
}

/** 规则柱状图 Tooltip：指标名称与数值单行展示。 */
function RulesBarChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: ReadonlyArray<{ value?: number }>
  label?: string
}) {
  if (!active || payload == null || payload.length === 0) return null
  const value = payload[0]?.value ?? 0
  const text = label != null && label !== '' ? `${label}: ${value}` : String(value)
  return <div className="minerva-overview__bar-tooltip">{text}</div>
}

/** 规则库全量统计柱状图。 */
function RulesStatsBarChart(): ReactNode {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()

  const statsQuery = useQuery({
    queryKey: ['ruleBaseOverviewStats', workspaceId],
    queryFn: () => getRuleBaseOverviewStats(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const chartData = useMemo(() => {
    const stats = statsQuery.data
    if (stats == null) return []
    return [
      {
        key: 'engineering',
        name: t('rules.overview.kpiEngineering'),
        value: stats.engineering_codes.length,
      },
      {
        key: 'subject',
        name: t('rules.overview.kpiSubject'),
        value: stats.subject_codes.length,
      },
      {
        key: 'docType',
        name: t('rules.overview.kpiDocType'),
        value: stats.document_type_codes.length,
      },
      {
        key: 'rules',
        name: t('rules.overview.kpiRules'),
        value: stats.rule_count,
      },
    ]
  }, [statsQuery.data, t])

  const hasData = chartData.length > 0
  const { chartBoxRef, chartBoxW } = useChartBoxWidth(hasData)

  return (
    <OverviewChartCard
      title={t('overview.rulesChartTitle')}
      pending={statsQuery.isPending}
      error={statsQuery.error}
      empty={t('overview.rulesChartEmpty')}
      hasData={hasData}
    >
      <div ref={chartBoxRef} className="minerva-overview__chart-wrap">
        {chartBoxW > 0 ? (
          <BarChart
            width={chartBoxW}
            height={240}
            data={chartData}
            margin={{ top: 8, right: 8, left: 0, bottom: 4 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="var(--minerva-border, #2a3f58)" opacity={0.45} />
            <XAxis
              dataKey="name"
              tick={{ fill: 'var(--minerva-ink-muted, #94a3b8)', fontSize: 10 }}
              interval={0}
              angle={-18}
              textAnchor="end"
              height={52}
            />
            <YAxis
              width={36}
              allowDecimals={false}
              tick={{ fill: 'var(--minerva-ink-muted, #94a3b8)', fontSize: 10 }}
            />
            <RechartsTooltip
              cursor={{ fill: 'var(--minerva-overview-bar-cursor, rgba(56, 189, 248, 0.12))' }}
              content={<RulesBarChartTooltip />}
            />
            <Bar
              dataKey="value"
              radius={[6, 6, 0, 0]}
              maxBarSize={48}
              isAnimationActive={false}
              activeBar={{ opacity: 0.88, strokeWidth: 0 }}
            >
              {chartData.map((entry, index) => (
                <Cell key={entry.key} fill={RULES_BAR_COLORS[index % RULES_BAR_COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        ) : (
          <div className="minerva-overview__chart-measure" aria-hidden />
        )}
      </div>
    </OverviewChartCard>
  )
}

/** 工作区概览页：快捷应用入口 + 三列统计图表。 */
export function OverviewPage(): ReactNode {
  const { t } = useTranslation()
  const navigate = useNavigate()

  return (
    <div className="minerva-overview">
      <div className="minerva-overview__row-scroll minerva-scrollbar-thin">
        <div className="minerva-overview__row">
          {OVERVIEW_APPS.map((item) => (
            <OverviewAppCard
              key={item.key}
              item={item}
              title={t(item.titleKey)}
              description={t(item.descKey)}
              onOpen={(path) => void navigate(path)}
            />
          ))}
        </div>
      </div>
      <div className="minerva-overview__charts">
        <div className="minerva-overview__chart-slot">
          <AgentTokenUsageChart />
        </div>
        <div className="minerva-overview__chart-slot">
          <OcrTaskDailyChart />
        </div>
        <div className="minerva-overview__chart-slot">
          <RulesStatsBarChart />
        </div>
      </div>
    </div>
  )
}
