/**
 * 消息附件图片缩略图，支持 Ant Design 点击放大预览。
 */
import { Image } from 'antd'
import { useTranslation } from 'react-i18next'
import { resolveAgentAttachmentUrl, type AgentMessageAttachmentOut } from '@/api/agent'

type Props = {
  att: AgentMessageAttachmentOut
}

export function AgentAttachmentImage({ att }: Props) {
  const { t } = useTranslation()
  const src = resolveAgentAttachmentUrl(att.download_url)
  if (!src) return null
  return (
    <Image
      rootClassName="agents-page__msg-attachment-wrap"
      className="agents-page__msg-attachment-img"
      src={src}
      alt={att.file_name ?? t('agents.vision.imageAlt')}
      preview={{ mask: t('agents.attachment.preview') }}
    />
  )
}
