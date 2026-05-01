/** Provides create/edit form modal for one celery job. */

import { Button, Drawer, Form, Input, Select, Space, Typography } from 'antd'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { CronBuilder } from './CronBuilder'
import type { CeleryJob, CeleryJobCreateBody, CeleryJobPatchBody } from './types'
import './CeleryFormModal.css'

type CeleryFormModalMode = 'create' | 'edit'

type CeleryFormValues = {
  name: string
  task_code: string
  task: string
  cron: string
  timezone: string
  enabled?: boolean
  args_json: string
  kwargs_json: string
  remark: string
}

type CeleryFormSubmitPayload = CeleryJobCreateBody | CeleryJobPatchBody

const { Text } = Typography

/** Default positional-args JSON when opening the create drawer (maps to Celery ``*args``). */
const DEFAULT_CREATE_ARGS_JSON = JSON.stringify(['minerva'], null, 2)

/** Default keyword-args JSON when opening the create drawer (maps to Celery ``**kwargs``). */
const DEFAULT_CREATE_KWARGS_JSON = JSON.stringify({ source: 'scheduler' }, null, 2)

type CeleryFormModalProps = {
  open: boolean
  mode: CeleryFormModalMode
  submitting: boolean
  job?: CeleryJob | null
  onCancel: () => void
  onSubmit: (payload: CeleryFormSubmitPayload) => Promise<void>
}

/** Converts one JSON-serializable value to textarea text. */
function stringifyJsonField(value: unknown): string {
  if (value == null) return ''
  return JSON.stringify(value, null, 2)
}

/** Returns true when cron has 5 (legacy) or 6 (with second) space-separated segments. */
function isValidCronExpression(value: string): boolean {
  const trimmed = value.trim()
  if (trimmed === '') return false
  const parts = trimmed.split(/\s+/)
  if (parts.length !== 5 && parts.length !== 6) return false
  return parts.every((part) => part !== '')
}

/** Parses textarea JSON text; empty input returns null. */
function parseOptionalJson(value: string): unknown | null {
  const trimmed = value.trim()
  if (trimmed === '') return null
  return JSON.parse(trimmed) as unknown
}

/** Normalizes one optional text input to string-or-null API shape. */
function toNullableText(value: string): string | null {
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

/** Converts one form model into create/patch API payload shape. */
function toSubmitPayload(values: CeleryFormValues): CeleryFormSubmitPayload {
  const argsJsonValue = parseOptionalJson(values.args_json)
  const kwargsJsonValue = parseOptionalJson(values.kwargs_json)
  return {
    name: values.name.trim(),
    task_code: values.task_code.trim(),
    task: values.task.trim(),
    cron: toNullableText(values.cron),
    timezone: toNullableText(values.timezone),
    enabled: values.enabled ?? true,
    args_json: (argsJsonValue as Record<string, unknown> | unknown[] | null) ?? null,
    kwargs_json: (kwargsJsonValue as Record<string, unknown> | null) ?? null,
    remark: toNullableText(values.remark),
  }
}

/** Renders the add/edit modal and validates cron/json fields before submit. */
export function CeleryFormModal(props: CeleryFormModalProps) {
  const { t } = useTranslation()
  const [form] = Form.useForm<CeleryFormValues>()

  useEffect(() => {
    if (!props.open) return
    if (props.mode === 'edit' && props.job != null) {
      form.setFieldsValue({
        name: props.job.name ?? '',
        task_code: props.job.task_code ?? '',
        task: props.job.task ?? '',
        cron: props.job.cron ?? '',
        timezone: props.job.timezone ?? 'Asia/Shanghai',
        enabled: props.job.enabled,
        args_json: stringifyJsonField(props.job.args_json),
        kwargs_json: stringifyJsonField(props.job.kwargs_json),
        remark: props.job.remark ?? '',
      })
      return
    }
    form.setFieldsValue({
      name: '',
      task_code: '',
      task: '',
      cron: '0 * * * * *',
      timezone: 'Asia/Shanghai',
      enabled: true,
      args_json: DEFAULT_CREATE_ARGS_JSON,
      kwargs_json: DEFAULT_CREATE_KWARGS_JSON,
      remark: '',
    })
  }, [form, props.job, props.mode, props.open])

  /** Validates cron as 5-part (legacy) or 6-part (second-first) expression. */
  const validateCron = (_: unknown, value: string | undefined) => {
    const raw = value ?? ''
    if (isValidCronExpression(raw)) return Promise.resolve()
    return Promise.reject(new Error(t('settings.celery.cronInvalid')))
  }

  /** Validates args_json as a JSON object/array when provided. */
  const validateArgsJson = (_: unknown, value: string | undefined) => {
    const raw = (value ?? '').trim()
    if (raw === '') return Promise.resolve()
    try {
      const parsed = JSON.parse(raw) as unknown
      if (Array.isArray(parsed) || (parsed != null && typeof parsed === 'object')) {
        return Promise.resolve()
      }
      return Promise.reject(new Error(t('settings.celery.argsJsonInvalid')))
    } catch {
      return Promise.reject(new Error(t('settings.celery.argsJsonInvalid')))
    }
  }

  /** Validates kwargs_json as a JSON object when provided. */
  const validateKwargsJson = (_: unknown, value: string | undefined) => {
    const raw = (value ?? '').trim()
    if (raw === '') return Promise.resolve()
    try {
      const parsed = JSON.parse(raw) as unknown
      if (parsed != null && !Array.isArray(parsed) && typeof parsed === 'object') {
        return Promise.resolve()
      }
      return Promise.reject(new Error(t('settings.celery.kwargsJsonInvalid')))
    } catch {
      return Promise.reject(new Error(t('settings.celery.kwargsJsonInvalid')))
    }
  }

  /** Submits normalized payload to parent and lets parent refresh list. */
  const handleFinish = async (values: CeleryFormValues) => {
    await props.onSubmit(toSubmitPayload(values))
  }

  return (
    <Drawer
      width={820}
      destroyOnClose
      open={props.open}
      placement="right"
      title={props.mode === 'create' ? t('settings.celery.createModalTitle') : t('settings.celery.editModalTitle')}
      classNames={{ body: 'minerva-scrollbar-styled' }}
      onClose={props.onCancel}
      extra={
        <Space size="middle">
          <Button onClick={props.onCancel}>{t('common.cancel')}</Button>
          <Button type="primary" loading={props.submitting} onClick={() => void form.submit()}>
            {props.mode === 'create' ? t('settings.celery.drawerSubmitCreate') : t('common.save')}
          </Button>
        </Space>
      }
    >
      <Form<CeleryFormValues> form={form} layout="vertical" onFinish={(values) => void handleFinish(values)}>
        <Form.Item
          name="name"
          label={t('settings.celery.fieldName')}
          rules={[{ required: true, message: t('settings.celery.fieldNameRequired') }]}
        >
          <Input allowClear autoComplete="off" />
        </Form.Item>
        <Form.Item
          name="task_code"
          label={t('settings.celery.fieldTaskCode')}
          rules={[{ required: true, message: t('settings.celery.fieldTaskCodeRequired') }]}
        >
          <Input allowClear autoComplete="off" />
        </Form.Item>
        <Form.Item
          name="task"
          label={t('settings.celery.fieldTask')}
          rules={[{ required: true, message: t('settings.celery.fieldTaskRequired') }]}
        >
          <Input allowClear autoComplete="off" />
        </Form.Item>
        <Form.Item
          label={t('settings.celery.fieldCron')}
          extra={<Text type="secondary">{t('settings.celery.cronBuilderHint')}</Text>}
        >
          <Space.Compact block className="minerva-celery-form-cron-compact">
            <Form.Item
              name="cron"
              noStyle
              rules={[
                { required: true, message: t('settings.celery.fieldCronRequired') },
                { validator: validateCron },
              ]}
            >
              <Input allowClear autoComplete="off" />
            </Form.Item>
            <Form.Item shouldUpdate noStyle>
              {({ getFieldValue, setFieldValue }) => (
                <CronBuilder
                  layout="inline"
                  value={getFieldValue('cron')}
                  previewTimezone={getFieldValue('timezone')}
                  disabled={props.submitting}
                  onChange={(cronValue) => setFieldValue('cron', cronValue)}
                />
              )}
            </Form.Item>
          </Space.Compact>
        </Form.Item>
        <Form.Item name="timezone" label={t('settings.celery.fieldTimezone')}>
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            options={[
              { value: 'Asia/Shanghai', label: 'Asia/Shanghai' },
              { value: 'UTC', label: 'UTC' },
              { value: 'Asia/Singapore', label: 'Asia/Singapore' },
              { value: 'America/New_York', label: 'America/New_York' },
              { value: 'Europe/London', label: 'Europe/London' },
            ]}
          />
        </Form.Item>
        <Form.Item
          name="enabled"
          label={t('settings.celery.fieldEnabled')}
          rules={[{ required: true, message: t('settings.celery.fieldEnabledRequired') }]}
        >
          <Select
            allowClear
            options={[
              { value: true, label: t('settings.celery.enabledText') },
              { value: false, label: t('settings.celery.disabledText') },
            ]}
          />
        </Form.Item>
        <Form.Item
          name="args_json"
          label={t('settings.celery.fieldArgsJson')}
          rules={[{ validator: validateArgsJson }]}
          extra={<Text type="secondary">{t('settings.celery.fieldArgsJsonExtra')}</Text>}
        >
          <Input.TextArea
            allowClear
            autoSize={{ minRows: 3, maxRows: 8 }}
            classNames={{ textarea: 'minerva-scrollbar-styled' }}
            placeholder={t('settings.celery.fieldArgsJsonPh')}
          />
        </Form.Item>
        <Form.Item
          name="kwargs_json"
          label={t('settings.celery.fieldKwargsJson')}
          rules={[{ validator: validateKwargsJson }]}
          extra={<Text type="secondary">{t('settings.celery.fieldKwargsJsonExtra')}</Text>}
        >
          <Input.TextArea
            allowClear
            autoSize={{ minRows: 3, maxRows: 8 }}
            classNames={{ textarea: 'minerva-scrollbar-styled' }}
            placeholder={t('settings.celery.fieldKwargsJsonPh')}
          />
        </Form.Item>
        <Form.Item name="remark" label={t('settings.celery.fieldRemark')}>
          <Input.TextArea allowClear autoSize={{ minRows: 2, maxRows: 6 }} classNames={{ textarea: 'minerva-scrollbar-styled' }} />
        </Form.Item>
      </Form>
    </Drawer>
  )
}
