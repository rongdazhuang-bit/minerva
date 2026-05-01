/**
 * RuoYi 风格 Cron 可视化生成弹层：按秒/分/时/日/月/周分栏配置，输出 Celery 6 段表达式并预览最近触发时间。
 * 「年」页签仅说明本系统不写第 7 段；「日」「周」同时具体时自动将「周」置为 *。
 */

import {
  Alert,
  Button,
  Input,
  InputNumber,
  Modal,
  Radio,
  Select,
  Space,
  Tabs,
  Typography,
} from 'antd'
import CronExpressionParser from 'cron-parser'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  type CronGenSegmentState,
  type CronGeneratorFullState,
  type CronGenTabKey,
  buildSixFieldCron,
  getDefaultCronGeneratorState,
  parseCronToGeneratorState,
} from './cronExpressionGeneratorModel'
import './CronExpressionGeneratorModal.css'

const BOUNDS: Record<Exclude<CronGenTabKey, 'year'>, { min: number; max: number }> = {
  second: { min: 0, max: 59 },
  minute: { min: 0, max: 59 },
  hour: { min: 0, max: 23 },
  day: { min: 1, max: 31 },
  month: { min: 1, max: 12 },
  weekday: { min: 0, max: 6 },
}

type CronExpressionGeneratorModalProps = {
  open: boolean
  /** 打开时作为解析初值（5 或 6 段 Celery Cron）。 */
  initialCron?: string | null
  /** 预览「最近运行时间」所用的 IANA 时区；空则用运行环境默认。 */
  previewTimezone?: string | null
  disabled?: boolean
  onConfirm: (cronSixField: string) => void
  onCancel: () => void
}

/**
 * 根据起止范围生成 {@link Select} 数字选项。
 */
function numberOptions(min: number, max: number) {
  const out: { value: number; label: string }[] = []
  for (let v = min; v <= max; v += 1) out.push({ value: v, label: String(v) })
  return out
}

/**
 * 计算当前表达式下随后若干次触发时间（解析失败返回空数组）。
 */
function computeNextRunLabels(expression: string, tz: string | null | undefined, locale: string): string[] {
  const trimmed = expression.trim()
  if (!trimmed) return []
  try {
    const interval = CronExpressionParser.parse(trimmed, {
      currentDate: new Date(),
      tz: tz != null && tz.trim() !== '' ? tz.trim() : undefined,
      strict: false,
    })
    const labels: string[] = []
    for (let i = 0; i < 5; i += 1) {
      const d = interval.next().toDate()
      labels.push(d.toLocaleString(locale === 'zh-CN' ? 'zh-CN' : 'en-GB', { hour12: false }))
    }
    return labels
  } catch {
    return []
  }
}

type SegmentPanelProps = {
  tab: Exclude<CronGenTabKey, 'year'>
  state: CronGenSegmentState
  disabled?: boolean
  onChange: (next: CronGenSegmentState) => void
}

/**
 * 单个时间维度页签：通配 / 不指定 / 周期 / 从…每隔… / 指定列表。
 */
function SegmentConfigPanel(props: SegmentPanelProps) {
  const { t } = useTranslation()
  const { tab, state, disabled, onChange } = props
  const b = BOUNDS[tab]
  const opts = useMemo(() => numberOptions(b.min, b.max), [b.min, b.max])
  const weekdayOpts = useMemo(
    () =>
      numberOptions(0, 6).map((o) => ({
        value: o.value,
        label: `${t(`settings.celery.cronGen.weekday.${o.value}`)} (${o.value})`,
      })),
    [t],
  )
  const listSelectOptions = tab === 'weekday' ? weekdayOpts : opts

  /** 合并局部字段并上抛。 */
  const patch = (partial: Partial<CronGenSegmentState>) => {
    onChange({ ...state, ...partial })
  }

  const showUnspecified = tab !== 'second'

  return (
    <div className="minerva-cron-gen-segment">
      <Radio.Group
        disabled={disabled}
        value={state.mode}
        onChange={(ev) => patch({ mode: ev.target.value as CronGenSegmentState['mode'] })}
      >
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Radio value="every">{t('settings.celery.cronGen.mode.every')}</Radio>
          {showUnspecified ? (
            <Radio value="unspecified">{t('settings.celery.cronGen.mode.unspecified')}</Radio>
          ) : null}
          <Radio value="range">
            <Space wrap size="small" align="center">
              <span>{t('settings.celery.cronGen.mode.range')}</span>
              <InputNumber
                size="small"
                min={b.min}
                max={b.max}
                disabled={disabled || state.mode !== 'range'}
                value={state.rangeLo}
                onChange={(v) => patch({ rangeLo: v ?? b.min })}
              />
              <span>—</span>
              <InputNumber
                size="small"
                min={b.min}
                max={b.max}
                disabled={disabled || state.mode !== 'range'}
                value={state.rangeHi}
                onChange={(v) => patch({ rangeHi: v ?? b.max })}
              />
            </Space>
          </Radio>
          <Radio value="interval">
            <Space wrap size="small" align="center">
              <span>{t('settings.celery.cronGen.mode.interval')}</span>
              <InputNumber
                size="small"
                min={b.min}
                max={b.max}
                disabled={disabled || state.mode !== 'interval'}
                value={state.intervalStart}
                onChange={(v) => patch({ intervalStart: v ?? 0 })}
              />
              <span>{t('settings.celery.cronGen.intervalEvery')}</span>
              <InputNumber
                size="small"
                min={1}
                max={tab === 'hour' ? 23 : tab === 'day' ? 31 : tab === 'month' ? 12 : 59}
                disabled={disabled || state.mode !== 'interval'}
                value={state.intervalStep}
                onChange={(v) => patch({ intervalStep: Math.max(1, v ?? 1) })}
              />
            </Space>
          </Radio>
          <Radio value="list">
            <Space direction="vertical" size="small" style={{ width: '100%' }}>
              <span>{t('settings.celery.cronGen.mode.list')}</span>
              <Select
                mode="multiple"
                allowClear
                disabled={disabled || state.mode !== 'list'}
                style={{ maxWidth: 420 }}
                options={listSelectOptions}
                value={state.list}
                maxTagCount="responsive"
                placeholder={t('settings.celery.cronGen.listPlaceholder')}
                onChange={(vals) => patch({ list: (vals as number[]) ?? [] })}
              />
            </Space>
          </Radio>
        </Space>
      </Radio.Group>
    </div>
  )
}

/**
 * 受控弹层：确认时仅回传 6 段串；重置恢复默认样例状态。
 */
export function CronExpressionGeneratorModal(props: CronExpressionGeneratorModalProps) {
  const { t, i18n } = useTranslation()
  const [state, setState] = useState<CronGeneratorFullState>(() => getDefaultCronGeneratorState())

  useEffect(() => {
    if (!props.open) return
    setState(parseCronToGeneratorState(props.initialCron))
  }, [props.open, props.initialCron])

  const cronStr = useMemo(() => buildSixFieldCron(state), [state])
  const segments = useMemo(() => cronStr.split(/\s+/), [cronStr])
  const nextRuns = useMemo(
    () => computeNextRunLabels(cronStr, props.previewTimezone, i18n.language),
    [cronStr, props.previewTimezone, i18n.language],
  )

  const tabItems = useMemo(() => {
    const segmentTabs = (
      [
        ['second', 'settings.celery.cronGen.tab.second'],
        ['minute', 'settings.celery.cronGen.tab.minute'],
        ['hour', 'settings.celery.cronGen.tab.hour'],
        ['day', 'settings.celery.cronGen.tab.day'],
        ['month', 'settings.celery.cronGen.tab.month'],
        ['weekday', 'settings.celery.cronGen.tab.weekday'],
      ] as const
    ).map(([key, labelKey]) => ({
      key,
      label: t(labelKey),
      children: (
        <SegmentConfigPanel
          tab={key}
          state={state[key]}
          disabled={props.disabled}
          onChange={(next) =>
            setState((prev) => ({
              ...prev,
              [key]: next,
            }))
          }
        />
      ),
    }))
    return [
      ...segmentTabs,
      {
        key: 'year',
        label: t('settings.celery.cronGen.tab.year'),
        children: (
          <Alert
            type="info"
            showIcon
            message={t('settings.celery.cronGen.yearTitle')}
            description={t('settings.celery.cronGen.yearBody')}
          />
        ),
      },
    ]
  }, [state, props.disabled, t])

  return (
    <Modal
      open={props.open}
      title={t('settings.celery.cronGen.title')}
      onCancel={props.onCancel}
      width={720}
      className="minerva-cron-gen-modal"
      footer={null}
      destroyOnClose
    >
      <Tabs className="minerva-cron-gen-tabs" items={tabItems} />

      <div className="minerva-cron-gen-preview">
        <Typography.Text strong>{t('settings.celery.cronGen.previewTitle')}</Typography.Text>
        <div className="minerva-cron-gen-preview__grid">
          {(
            [
              'settings.celery.cronGen.col.second',
              'settings.celery.cronGen.col.minute',
              'settings.celery.cronGen.col.hour',
              'settings.celery.cronGen.col.day',
              'settings.celery.cronGen.col.month',
              'settings.celery.cronGen.col.weekday',
              'settings.celery.cronGen.col.year',
            ] as const
          ).map((labelKey, idx) => (
            <div key={labelKey}>
              <div className="minerva-cron-gen-preview__cell-label">{t(labelKey)}</div>
              <div className="minerva-cron-gen-preview__cell-value">
                {idx < 6 ? (segments[idx] ?? '—') : '—'}
              </div>
            </div>
          ))}
        </div>
        <Typography.Text type="secondary">{t('settings.celery.cronGen.fullLabel')}</Typography.Text>
        <Input readOnly value={cronStr} style={{ marginTop: 6, fontFamily: 'monospace' }} />
        <div className="minerva-cron-gen-next-runs">
          <Typography.Text strong>{t('settings.celery.cronGen.nextRuns')}</Typography.Text>
          {nextRuns.length > 0 ? (
            <ul>
              {nextRuns.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          ) : (
            <Typography.Text type="secondary">{t('settings.celery.cronGen.nextRunsEmpty')}</Typography.Text>
          )}
        </div>
      </div>

      <div className="minerva-cron-gen-footer">
        <Button onClick={props.onCancel} disabled={props.disabled}>
          {t('common.cancel')}
        </Button>
        <Button
          onClick={() => setState(getDefaultCronGeneratorState())}
          disabled={props.disabled}
        >
          {t('settings.celery.cronGen.reset')}
        </Button>
        <Button
          type="primary"
          disabled={props.disabled}
          onClick={() => props.onConfirm(cronStr)}
        >
          {t('settings.celery.cronGen.confirm')}
        </Button>
      </div>
    </Modal>
  )
}
