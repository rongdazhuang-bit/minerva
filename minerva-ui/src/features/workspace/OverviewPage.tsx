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

  CartesianGrid,

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

import { useAuth } from '@/app/AuthContext'

import './OverviewPage.css'



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



/** 智能体近 7 日 token 用量折线图（按 token 类型分 series）。 */

function AgentTokenUsageChart(): ReactNode {

  const { t } = useTranslation()

  const { workspaceId } = useAuth()

  const chartBoxRef = useRef<HTMLDivElement | null>(null)

  const [chartBoxW, setChartBoxW] = useState(0)



  const dailyQuery = useQuery({

    queryKey: ['agentOverviewUsageDailyStats', workspaceId],

    queryFn: () => getAgentOverviewUsageDailyStats(workspaceId!),

    enabled: Boolean(workspaceId),

  })



  const chartData = useMemo(() => dailyQuery.data?.items ?? [], [dailyQuery.data?.items])



  useLayoutEffect(() => {

    if (chartData.length === 0) {

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

  }, [workspaceId, chartData.length])



  const chartPending = dailyQuery.isPending

  const dailyErr = dailyQuery.error



  return (

    <Card

      size="small"

      variant="borderless"

      className="minerva-overview__chart-card"

      title={t('overview.tokenChartTitle')}

    >

      {dailyErr != null && (

        <Alert

          type="warning"

          showIcon

          message={dailyErr instanceof ApiError ? dailyErr.message : t('common.error')}

          style={{ marginBottom: 12 }}

        />

      )}

      <Spin spinning={chartPending}>

        {!chartPending && dailyErr == null && chartData.length > 0 && (

          <div ref={chartBoxRef} className="minerva-overview__chart-wrap">

            {chartBoxW > 0 ? (

              <LineChart

                width={chartBoxW}

                height={280}

                data={chartData}

                margin={{ top: 8, right: 16, left: 0, bottom: 8 }}

              >

                <CartesianGrid strokeDasharray="3 3" stroke="var(--minerva-border, #2a3f58)" opacity={0.45} />

                <XAxis

                  dataKey="date"

                  tickFormatter={(v) => (typeof v === 'string' && v.length >= 10 ? v.slice(5) : String(v))}

                  tick={{ fill: 'var(--minerva-ink-muted, #94a3b8)', fontSize: 11 }}

                />

                <YAxis

                  width={48}

                  tickFormatter={(v) => formatTokenCount(Number(v))}

                  tick={{ fill: 'var(--minerva-ink-muted, #94a3b8)', fontSize: 11 }}

                />

                <RechartsTooltip

                  contentStyle={{

                    background: 'var(--minerva-surface, #1a2836)',

                    borderColor: 'var(--minerva-border, #2a3f58)',

                  }}

                  formatter={(value) => formatTokenCount(Number(value ?? 0))}

                />

                <Legend wrapperStyle={{ fontSize: 12 }} />

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

        )}

        {!chartPending && dailyErr == null && chartData.length === 0 && (

          <Empty description={t('overview.tokenChartEmpty')} style={{ color: 'var(--minerva-ink)' }} />

        )}

      </Spin>

    </Card>

  )

}



/** 工作区概览页：顶部单行快捷应用入口 + 智能体 token 用量曲线。 */

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

      <AgentTokenUsageChart />

    </div>

  )

}


