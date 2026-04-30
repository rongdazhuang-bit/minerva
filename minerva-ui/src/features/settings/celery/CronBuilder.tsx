/** Renders a lightweight 5-part cron expression builder. */

import { Form, Select, Space, Typography } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

type CronPartKey = 'minute' | 'hour' | 'dayOfMonth' | 'month' | 'dayOfWeek'

type CronParts = {
  minute: string
  hour: string
  dayOfMonth: string
  month: string
  dayOfWeek: string
}

type CronBuilderProps = {
  value?: string | null
  disabled?: boolean
  onChange: (value: string) => void
}

const DEFAULT_CRON_PARTS: CronParts = {
  minute: '*',
  hour: '*',
  dayOfMonth: '*',
  month: '*',
  dayOfWeek: '*',
}

/** Parses one cron string into 5 parts if the expression is basic-valid. */
function parseCronParts(value: string | null | undefined): CronParts | null {
  const normalized = (value ?? '').trim()
  if (normalized === '') return null
  const segments = normalized.split(/\s+/)
  if (segments.length !== 5) return null
  const [minute, hour, dayOfMonth, month, dayOfWeek] = segments
  return { minute, hour, dayOfMonth, month, dayOfWeek }
}

/** Converts 5 cron parts into a space-separated cron string. */
function stringifyCronParts(parts: CronParts): string {
  return [parts.minute, parts.hour, parts.dayOfMonth, parts.month, parts.dayOfWeek].join(' ')
}

/** Normalizes a cleared selector value back to wildcard for one part. */
function normalizePartValue(value: string | undefined): string {
  const next = value?.trim()
  return next == null || next === '' ? '*' : next
}

/** Creates static options list for one cron part selector. */
function toSelectOptions(values: string[]) {
  return values.map((item) => ({ value: item, label: item }))
}

/** Hosts 5 selectors and emits a cron string whenever a selector changes. */
export function CronBuilder(props: CronBuilderProps) {
  const { t } = useTranslation()
  const [parts, setParts] = useState<CronParts>(() => parseCronParts(props.value) ?? DEFAULT_CRON_PARTS)

  const minuteOptions = useMemo(
    () => toSelectOptions(['*', '*/1', '*/5', '*/10', '*/15', '*/30', '0', '15', '30', '45']),
    [],
  )
  const hourOptions = useMemo(() => toSelectOptions(['*', '*/1', '*/2', '*/6', '0', '8', '12', '18', '23']), [])
  const dayOfMonthOptions = useMemo(() => toSelectOptions(['*', '1', '5', '10', '15', '20', '25', '28', 'L']), [])
  const monthOptions = useMemo(
    () => toSelectOptions(['*', '1', '3', '6', '9', '12', '1-6', '7-12']),
    [],
  )
  const dayOfWeekOptions = useMemo(() => toSelectOptions(['*', '0', '1', '2', '3', '4', '5', '6', '1-5']), [])

  useEffect(() => {
    const parsed = parseCronParts(props.value)
    if (parsed == null) return
    setParts(parsed)
  }, [props.value])

  /** Updates one part and pushes full cron value to parent form. */
  const handlePartChange = (key: CronPartKey, nextValue?: string) => {
    setParts((prev) => {
      const next: CronParts = {
        ...prev,
        [key]: normalizePartValue(nextValue),
      }
      props.onChange(stringifyCronParts(next))
      return next
    })
  }

  return (
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      <Typography.Text type="secondary">{t('settings.celery.cronBuilderHint')}</Typography.Text>
      <Space wrap size={8}>
        <Form.Item label={t('settings.celery.cronMinute')} style={{ marginBottom: 0 }}>
          <Select
            allowClear
            showSearch
            style={{ width: 120 }}
            disabled={props.disabled}
            value={parts.minute}
            options={minuteOptions}
            onChange={(value) => handlePartChange('minute', value)}
          />
        </Form.Item>
        <Form.Item label={t('settings.celery.cronHour')} style={{ marginBottom: 0 }}>
          <Select
            allowClear
            showSearch
            style={{ width: 120 }}
            disabled={props.disabled}
            value={parts.hour}
            options={hourOptions}
            onChange={(value) => handlePartChange('hour', value)}
          />
        </Form.Item>
        <Form.Item label={t('settings.celery.cronDayOfMonth')} style={{ marginBottom: 0 }}>
          <Select
            allowClear
            showSearch
            style={{ width: 120 }}
            disabled={props.disabled}
            value={parts.dayOfMonth}
            options={dayOfMonthOptions}
            onChange={(value) => handlePartChange('dayOfMonth', value)}
          />
        </Form.Item>
        <Form.Item label={t('settings.celery.cronMonth')} style={{ marginBottom: 0 }}>
          <Select
            allowClear
            showSearch
            style={{ width: 120 }}
            disabled={props.disabled}
            value={parts.month}
            options={monthOptions}
            onChange={(value) => handlePartChange('month', value)}
          />
        </Form.Item>
        <Form.Item label={t('settings.celery.cronDayOfWeek')} style={{ marginBottom: 0 }}>
          <Select
            allowClear
            showSearch
            style={{ width: 120 }}
            disabled={props.disabled}
            value={parts.dayOfWeek}
            options={dayOfWeekOptions}
            onChange={(value) => handlePartChange('dayOfWeek', value)}
          />
        </Form.Item>
      </Space>
    </Space>
  )
}
