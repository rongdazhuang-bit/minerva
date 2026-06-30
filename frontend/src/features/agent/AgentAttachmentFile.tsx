/**
 * 非图片消息附件：文件名 + 下载链接。
 */
import { FileOutlined } from '@ant-design/icons'
import { Button } from 'antd'
import { useTranslation } from 'react-i18next'
import { resolveAgentAttachmentUrl, type AgentMessageAttachmentOut } from '@/api/agent'

type Props = {
  att: AgentMessageAttachmentOut
}

export function AgentAttachmentFile({ att }: Props) {
  const { t } = useTranslation()
  const href = resolveAgentAttachmentUrl(att.download_url)
  const label = att.file_name ?? att.object_key.split('/').pop() ?? t('agents.attachment.file')
  if (!href) {
    return (
      <div className="agents-page__msg-attachment-file">
        <FileOutlined aria-hidden />
        <span>{label}</span>
      </div>
    )
  }
  return (
    <div className="agents-page__msg-attachment-file">
      <FileOutlined aria-hidden />
      <Button type="link" size="small" href={href} target="_blank" rel="noopener noreferrer">
        {label}
      </Button>
    </div>
  )
}

export function isImageAttachment(att: AgentMessageAttachmentOut): boolean {
  if (att.kind === 'image') return true
  if (att.kind === 'file') return false
  return (att.content_type ?? '').toLowerCase().startsWith('image/')
}
