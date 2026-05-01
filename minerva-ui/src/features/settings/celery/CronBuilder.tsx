/** 在表单中打开受控 Cron 可视化生成器，并把生成的 6 段表达式写回父级字段。 */

import { Button, Space, Typography } from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CronExpressionGeneratorModal } from './CronExpressionGeneratorModal'

type CronBuilderProps = {
  value?: string | null
  disabled?: boolean
  /** 与任务时区一致时，用于「最近运行时间」预览。 */
  previewTimezone?: string | null
  onChange: (value: string) => void
  /**
   * ``inline``：仅渲染打开生成器的按钮与弹窗，用于与 Cron 输入框同一行排列。
   * ``stacked``：在下方展示说明文案与按钮（默认）。
   */
  layout?: 'stacked' | 'inline'
}

/**
 * 展示入口按钮并在弹窗中完成 Cron 配置；``stacked`` 时附带说明文案。
 */
export function CronBuilder(props: CronBuilderProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const layout = props.layout ?? 'stacked'

  /** 与 Cron 输入框并排时使用主按钮，视觉上贴近 Search 样式组合框。 */
  const triggerType = layout === 'inline' ? 'primary' : 'default'

  const openButton = (
    <Button type={triggerType} disabled={props.disabled} onClick={() => setOpen(true)}>
      {t('settings.celery.cronGen.openBuilder')}
    </Button>
  )

  const modal = (
    <CronExpressionGeneratorModal
      open={open}
      initialCron={props.value}
      previewTimezone={props.previewTimezone}
      disabled={props.disabled}
      onCancel={() => setOpen(false)}
      onConfirm={(cron) => {
        props.onChange(cron)
        setOpen(false)
      }}
    />
  )

  if (layout === 'inline') {
    return (
      <>
        {openButton}
        {modal}
      </>
    )
  }

  return (
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      <Typography.Text type="secondary">{t('settings.celery.cronBuilderHint')}</Typography.Text>
      {openButton}
      {modal}
    </Space>
  )
}
