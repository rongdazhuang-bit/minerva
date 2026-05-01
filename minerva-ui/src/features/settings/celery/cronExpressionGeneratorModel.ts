/**
 * 状态与字符串互转：面向 Celery 6 段（秒 分 时 日 月 周），不含 Quartz 第 7 段年。
 * 「日」「周」同时具体时自动保留「日」、将「周」强制为 *，避免非法组合。
 */

/** 各时间维度在生成器中的配置模式（与常见可视化 Cron 工具的单选分组一致）。 */
export type CronGenMode = 'every' | 'unspecified' | 'range' | 'interval' | 'list'

/** 七个页签对应字段；`year` 仅用于占位说明，不参与输出字符串。 */
export type CronGenTabKey = 'second' | 'minute' | 'hour' | 'day' | 'month' | 'weekday' | 'year'

/** 单个页签的持久化状态（数字类字段在对应模式下才生效）。 */
export type CronGenSegmentState = {
  mode: CronGenMode
  /** `range`：下限。 */
  rangeLo: number
  /** `range`：上限。 */
  rangeHi: number
  /** `interval`：起始值（秒/分/时/日为闭区间起点，月/周同理）。 */
  intervalStart: number
  /** `interval`：步长，须为正整数。 */
  intervalStep: number
  /** `list`：具体取值多选，会去重排序后序列化。 */
  list: number[]
}

/** 生成器完整状态：`year` 不包含在导出的 cron 串中。 */
export type CronGeneratorFullState = Record<CronGenTabKey, CronGenSegmentState>

const BOUNDS: Record<Exclude<CronGenTabKey, 'year'>, { min: number; max: number }> = {
  second: { min: 0, max: 59 },
  minute: { min: 0, max: 59 },
  hour: { min: 0, max: 23 },
  day: { min: 1, max: 31 },
  month: { min: 1, max: 12 },
  weekday: { min: 0, max: 6 },
}

/** 新建页签时的默认区间/步长，避免 InputNumber 出现 undefined。 */
const NUM_DEFAULT = { rangeLo: 0, rangeHi: 1, intervalStart: 0, intervalStep: 1 }

/**
 * 返回各字段的初始状态：与表单默认 `0 * * * * *` 一致。
 * `year` 段为「不指定」占位，不写入 Celery 表达式。
 */
export function getDefaultCronGeneratorState(): CronGeneratorFullState {
  return {
    second: { mode: 'list', ...NUM_DEFAULT, list: [0] },
    minute: { mode: 'every', ...NUM_DEFAULT, list: [0] },
    hour: { mode: 'every', ...NUM_DEFAULT, list: [0] },
    day: { mode: 'every', ...NUM_DEFAULT, list: [1] },
    month: { mode: 'every', ...NUM_DEFAULT, list: [1] },
    weekday: { mode: 'every', ...NUM_DEFAULT, list: [0] },
    year: { mode: 'unspecified', ...NUM_DEFAULT, list: [new Date().getFullYear()] },
  }
}

/**
 * 将整数限制在字段允许范围内，避免序列化出越界片段。
 */
function clamp(tab: Exclude<CronGenTabKey, 'year'>, n: number): number {
  const { min, max } = BOUNDS[tab]
  return Math.min(max, Math.max(min, Math.trunc(n)))
}

/**
 * 判断一段 cron 字段是否「非 * 通配」，用于日/周互斥规则。
 */
export function segmentLooksSpecific(segment: string): boolean {
  const s = segment.trim()
  return s !== '' && s !== '*'
}

/**
 * 将单个片段状态序列化为 cron 字段串（不含日/周互斥修正）。
 */
export function serializeSegment(tab: Exclude<CronGenTabKey, 'year'>, state: CronGenSegmentState): string {
  const { min } = BOUNDS[tab]
  switch (state.mode) {
    case 'every':
    case 'unspecified':
      return '*'
    case 'range': {
      let lo = clamp(tab, state.rangeLo)
      let hi = clamp(tab, state.rangeHi)
      if (lo > hi) [lo, hi] = [hi, lo]
      return `${lo}-${hi}`
    }
    case 'interval': {
      const step = Math.max(1, Math.trunc(state.intervalStep || 1))
      const start = clamp(tab, state.intervalStart)
      if (start === 0) {
        return `*/${step}`
      }
      return `${start}/${step}`
    }
    case 'list': {
      const raw = state.list.length > 0 ? state.list : [min]
      const sorted = [...new Set(raw.map((n) => clamp(tab, n)))].sort((a, b) => a - b)
      return sorted.join(',')
    }
    default:
      return '*'
  }
}

/**
 * 由完整状态生成 Celery 可用的 6 段表达式（空格分隔）。
 */
export function buildSixFieldCron(state: CronGeneratorFullState): string {
  const day = serializeSegment('day', state.day)
  let weekday = serializeSegment('weekday', state.weekday)
  if (segmentLooksSpecific(day) && segmentLooksSpecific(weekday)) {
    weekday = '*'
  }
  const second = serializeSegment('second', state.second)
  const minute = serializeSegment('minute', state.minute)
  const hour = serializeSegment('hour', state.hour)
  const month = serializeSegment('month', state.month)
  return [second, minute, hour, day, month, weekday].join(' ')
}

/**
 * 将可选的 5/6 段 cron 粗解析为生成器状态（无法识别的片段按 `every` 处理）。
 */
export function parseCronToGeneratorState(value: string | null | undefined): CronGeneratorFullState {
  const next = getDefaultCronGeneratorState()
  const trimmed = (value ?? '').trim()
  if (!trimmed) return next

  const parts = trimmed.split(/\s+/).filter(Boolean)
  let sec = '0'
  let min = '*'
  let hr = '*'
  let dom = '*'
  let mon = '*'
  let dow = '*'
  if (parts.length === 5) {
    ;[min, hr, dom, mon, dow] = parts
  } else if (parts.length === 6) {
    ;[sec, min, hr, dom, mon, dow] = parts
  } else {
    return next
  }

  next.second = segmentToState('second', sec, next.second)
  next.minute = segmentToState('minute', min, next.minute)
  next.hour = segmentToState('hour', hr, next.hour)
  next.day = segmentToState('day', dom, next.day)
  next.month = segmentToState('month', mon, next.month)
  next.weekday = segmentToState('weekday', dow, next.weekday)
  return next
}

/**
 * 把一段 cron 字符解析为 {@link CronGenSegmentState}，保留传入的 `fallback` 中的默认数字。
 */
function segmentToState(
  tab: Exclude<CronGenTabKey, 'year'>,
  segment: string,
  fallback: CronGenSegmentState,
): CronGenSegmentState {
  const s = segment.trim()
  if (s === '*' || s === '?') {
    return { ...fallback, mode: s === '?' ? 'unspecified' : 'every' }
  }
  const stepBoth = /^(\d+|\*)\/(\d+)$/.exec(s)
  if (stepBoth) {
    const startRaw = stepBoth[1]
    const step = Math.max(1, parseInt(stepBoth[2], 10))
    const start = startRaw === '*' ? 0 : clamp(tab, parseInt(startRaw, 10))
    return { ...fallback, mode: 'interval', intervalStart: start, intervalStep: step }
  }
  const range = /^(\d+)-(\d+)$/.exec(s)
  if (range) {
    return {
      ...fallback,
      mode: 'range',
      rangeLo: clamp(tab, parseInt(range[1], 10)),
      rangeHi: clamp(tab, parseInt(range[2], 10)),
    }
  }
  if (/^\d+(,\d+)*$/.test(s)) {
    const list = s.split(',').map((x) => clamp(tab, parseInt(x, 10)))
    return { ...fallback, mode: 'list', list }
  }
  const single = /^(\d+)$/.exec(s)
  if (single) {
    return { ...fallback, mode: 'list', list: [clamp(tab, parseInt(single[1], 10))] }
  }
  return { ...fallback, mode: 'every' }
}
