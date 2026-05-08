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
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type Dispatch,
  type SetStateAction,
} from 'react'
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

/** 将「日」号数限制在 1–31，供最近工作日 `nW` 输入使用。 */
function clampDayOfMonth(n: number): number {
  const { min, max } = BOUNDS.day
  return Math.min(max, Math.max(min, Math.trunc(n)))
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

/** 「指定」多选下拉的固定枚举：秒为 0–59（与 Quartz/Cron 秒域一致）。 */
const SECOND_SPECIFY_OPTIONS = numberOptions(0, 59)

/**
 * 返回当前页签在「指定」模式下的下拉选项（数字域按 {@link BOUNDS}；周附带本地化的星期文案）。
 */
function getListSelectOptions(
  tab: Exclude<CronGenTabKey, 'year'>,
  numericOpts: { value: number; label: string }[],
  weekdayOpts: { value: number; label: string }[],
): { value: number; label: string }[] {
  if (tab === 'weekday') return weekdayOpts
  if (tab === 'second') return SECOND_SPECIFY_OPTIONS
  return numericOpts
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

/** 供各 {@link SegmentConfigPanel} 读取整表状态；避免把 `state` 塞进 `Tabs` 的 `items` 导致面板重挂载、下拉一闪即关。 */
type CronGenModalContextValue = {
  state: CronGeneratorFullState
  setState: Dispatch<SetStateAction<CronGeneratorFullState>>
  disabled?: boolean
}

const CronGenModalContext = createContext<CronGenModalContextValue | null>(null)

/**
 * 读取 Cron 生成器弹层状态；须在 Provider 内使用。
 */
function useCronGenModalContext(): CronGenModalContextValue {
  const v = useContext(CronGenModalContext)
  if (v == null) {
    throw new Error('useCronGenModalContext: missing CronGenModalContext.Provider')
  }
  return v
}

type SegmentPanelProps = {
  tab: Exclude<CronGenTabKey, 'year'>
}

/**
 * 单个时间维度页签：通配 / 不指定 / 周期 / 从…每隔… / 指定列表。
 * 「指定」与多选 {@link Select} 同一行 flex 排布；{@link Select} 仍勿嵌在 {@link Radio} 节点内；下拉挂 `document.body`，滚动条样式见 `appLayoutScroll.css`。
 */
function SegmentConfigPanel(props: SegmentPanelProps) {
  const { t } = useTranslation()
  const { tab } = props
  const { state, setState, disabled } = useCronGenModalContext()
  const segmentState = state[tab]

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
  /** 「周」周期/第 n 周/最后一周 下拉里仅显示本地化星期名（与参考图一致，不带 0–6 数字后缀）。 */
  const weekdayNameOpts = useMemo(
    () =>
      numberOptions(0, 6).map((o) => ({
        value: o.value,
        label: t(`settings.celery.cronGen.weekday.${o.value}`),
      })),
    [t],
  )
  const listSelectOptions = useMemo(
    () => getListSelectOptions(tab, opts, weekdayOpts),
    [tab, opts, weekdayOpts],
  )

  /** 间隔步长上限：依字段取值范围（周字段此前误用 59，此处纠正为 6）。 */
  const intervalStepMax =
    tab === 'hour' ? 23 : tab === 'day' ? 31 : tab === 'month' ? 12 : tab === 'weekday' ? 6 : 59

  /** 合并当前页签片段并写回全局生成器状态。 */
  const patch = (partial: Partial<CronGenSegmentState>) => {
    setState((prev) => ({
      ...prev,
      [tab]: { ...prev[tab], ...partial },
    }))
  }

  const showUnspecified = tab !== 'second'
  const unitLabel = t(`settings.celery.cronGen.unit.${tab}`)
  /** 周字段为 0–6，周期/间隔文案不加「秒」类单位以免歧义。 */
  const showQuantityUnit = tab !== 'weekday'

  return (
    <div className="minerva-cron-gen-segment">
      <Radio.Group
        disabled={disabled}
        value={segmentState.mode}
        onChange={(ev) => patch({ mode: ev.target.value as CronGenSegmentState['mode'] })}
      >
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Radio value="every">
            <span className="minerva-cron-gen-every-line">
              <span className="minerva-cron-gen-every-line__tab">{t(`settings.celery.cronGen.tab.${tab}`)}</span>
              <span className="minerva-cron-gen-every-line__hint">
                {t('settings.celery.cronGen.everySeparator')}
                {t(
                  tab === 'day'
                    ? 'settings.celery.cronGen.wildcardHintDay'
                    : tab === 'weekday'
                      ? 'settings.celery.cronGen.wildcardHintWeek'
                      : 'settings.celery.cronGen.wildcardHint',
                )}
              </span>
            </span>
          </Radio>
          {showUnspecified ? (
            <Radio value="unspecified">{t('settings.celery.cronGen.mode.unspecified')}</Radio>
          ) : null}
          <Radio value="range">
            <Space wrap size="small" align="center">
              {tab === 'weekday' ? (
                <>
                  <span>{t('settings.celery.cronGen.weekMode.rangeLead')}</span>
                  <Select
                    size="small"
                    allowClear={false}
                    disabled={disabled || segmentState.mode !== 'range'}
                    className="minerva-cron-gen-weekday-select"
                    options={weekdayNameOpts}
                    value={segmentState.rangeLo}
                    getPopupContainer={() => document.body}
                    popupClassName="minerva-cron-gen-select-dropdown"
                    onChange={(v) => patch({ rangeLo: v ?? 0 })}
                  />
                  <span>{t('settings.celery.cronGen.rangeDash')}</span>
                  <Select
                    size="small"
                    allowClear={false}
                    disabled={disabled || segmentState.mode !== 'range'}
                    className="minerva-cron-gen-weekday-select"
                    options={weekdayNameOpts}
                    value={segmentState.rangeHi}
                    getPopupContainer={() => document.body}
                    popupClassName="minerva-cron-gen-select-dropdown"
                    onChange={(v) => patch({ rangeHi: v ?? 0 })}
                  />
                </>
              ) : (
                <>
                  <span>{t('settings.celery.cronGen.rangeLead')}</span>
                  <InputNumber
                    size="small"
                    min={b.min}
                    max={b.max}
                    disabled={disabled || segmentState.mode !== 'range'}
                    value={segmentState.rangeLo}
                    onChange={(v) => patch({ rangeLo: v ?? b.min })}
                  />
                  <span>{t('settings.celery.cronGen.rangeDash')}</span>
                  <InputNumber
                    size="small"
                    min={b.min}
                    max={b.max}
                    disabled={disabled || segmentState.mode !== 'range'}
                    value={segmentState.rangeHi}
                    onChange={(v) => patch({ rangeHi: v ?? b.max })}
                  />
                  {showQuantityUnit ? <span>{unitLabel}</span> : null}
                </>
              )}
            </Space>
          </Radio>
          {tab !== 'weekday' || segmentState.mode === 'interval' ? (
            <Radio value="interval">
              <Space wrap size="small" align="center">
                <span>{t('settings.celery.cronGen.intervalPrefix')}</span>
                <InputNumber
                  size="small"
                  min={b.min}
                  max={b.max}
                  disabled={disabled || segmentState.mode !== 'interval'}
                  value={segmentState.intervalStart}
                  onChange={(v) => patch({ intervalStart: v ?? 0 })}
                />
                {showQuantityUnit ? <span>{unitLabel}</span> : null}
                <span>{t('settings.celery.cronGen.intervalMiddle')}</span>
                <InputNumber
                  size="small"
                  min={1}
                  max={intervalStepMax}
                  disabled={disabled || segmentState.mode !== 'interval'}
                  value={segmentState.intervalStep}
                  onChange={(v) => patch({ intervalStep: Math.max(1, v ?? 1) })}
                />
                {showQuantityUnit ? <span>{unitLabel}</span> : null}
                <span>{t('settings.celery.cronGen.intervalSuffix')}</span>
              </Space>
            </Radio>
          ) : null}
          {tab === 'day' ? (
            <>
              <Radio value="dayNearestWeekday">
                <Space wrap size="small" align="center">
                  <span>{t('settings.celery.cronGen.dayMode.nearestWeekdayLead')}</span>
                  <InputNumber
                    size="small"
                    min={1}
                    max={31}
                    disabled={disabled || segmentState.mode !== 'dayNearestWeekday'}
                    value={segmentState.nearestWeekdayDom}
                    onChange={(v) =>
                      patch({ nearestWeekdayDom: clampDayOfMonth(v ?? segmentState.nearestWeekdayDom) })
                    }
                  />
                  <span>{t('settings.celery.cronGen.dayMode.nearestWeekdayTail')}</span>
                </Space>
              </Radio>
              <Radio value="dayLast">{t('settings.celery.cronGen.dayMode.lastOfMonth')}</Radio>
            </>
          ) : null}
          {tab === 'weekday' ? (
            <>
              <Radio value="weekNthDow">
                <Space wrap size="small" align="center">
                  <span>{t('settings.celery.cronGen.weekMode.nthLead')}</span>
                  <InputNumber
                    size="small"
                    min={1}
                    max={5}
                    disabled={disabled || segmentState.mode !== 'weekNthDow'}
                    value={segmentState.weekNthOrdinal}
                    onChange={(v) =>
                      patch({
                        weekNthOrdinal: Math.min(5, Math.max(1, Math.trunc(v ?? 1))),
                      })
                    }
                  />
                  <span>{t('settings.celery.cronGen.weekMode.nthMid')}</span>
                  <Select
                    size="small"
                    allowClear={false}
                    disabled={disabled || segmentState.mode !== 'weekNthDow'}
                    className="minerva-cron-gen-weekday-select"
                    options={weekdayNameOpts}
                    value={segmentState.weekNthDow}
                    getPopupContainer={() => document.body}
                    popupClassName="minerva-cron-gen-select-dropdown"
                    onChange={(v) => patch({ weekNthDow: v ?? 0 })}
                  />
                </Space>
              </Radio>
              <Radio value="weekLastDow">
                <Space wrap size="small" align="center">
                  <span>{t('settings.celery.cronGen.weekMode.lastWeekdayLead')}</span>
                  <Select
                    size="small"
                    allowClear={false}
                    disabled={disabled || segmentState.mode !== 'weekLastDow'}
                    className="minerva-cron-gen-weekday-select"
                    options={weekdayNameOpts}
                    value={segmentState.weekLastDow}
                    getPopupContainer={() => document.body}
                    popupClassName="minerva-cron-gen-select-dropdown"
                    onChange={(v) => patch({ weekLastDow: v ?? 0 })}
                  />
                </Space>
              </Radio>
            </>
          ) : null}
          <div className="minerva-cron-gen-specify-row">
            <Radio value="list">{t('settings.celery.cronGen.specifyLabel')}</Radio>
            {segmentState.mode === 'list' ? (
              <Select
                mode="multiple"
                allowClear
                disabled={disabled}
                className="minerva-cron-gen-specify-select"
                options={listSelectOptions}
                value={segmentState.list}
                maxTagCount="responsive"
                placeholder={t('settings.celery.cronGen.listPlaceholder')}
                getPopupContainer={() => document.body}
                popupMatchSelectWidth={false}
                popupClassName="minerva-cron-gen-select-dropdown"
                listHeight={256}
                onChange={(vals) => patch({ list: (vals as number[]) ?? [] })}
              />
            ) : null}
          </div>
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

  /** 仅随文案/禁用变化重建，避免 `state` 变更时 Tabs 整页重挂载。 */
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
      children: <SegmentConfigPanel tab={key} />,
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
  }, [t])

  const cronGenContextValue = useMemo(
    () => ({ state, setState, disabled: props.disabled }),
    [state, props.disabled],
  )

  return (
    <Modal
      open={props.open}
      title={t('settings.celery.cronGen.title')}
      onCancel={props.onCancel}
      width={880}
      className="minerva-cron-gen-modal"
      footer={null}
      destroyOnClose
    >
      <CronGenModalContext.Provider value={cronGenContextValue}>
        <Tabs className="minerva-cron-gen-tabs" items={tabItems} />

      <div className="minerva-cron-gen-preview">
        <Typography.Text strong className="minerva-cron-gen-preview__heading">
          {t('settings.celery.cronGen.previewTitle')}
        </Typography.Text>
        <div className="minerva-cron-gen-preview__main">
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
          <div className="minerva-cron-gen-preview__cron">
            <Typography.Text type="secondary">{t('settings.celery.cronGen.fullLabel')}</Typography.Text>
            <Input readOnly value={cronStr} className="minerva-cron-gen-preview__cron-input" />
          </div>
        </div>
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
      </CronGenModalContext.Provider>
    </Modal>
  )
}
