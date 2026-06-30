/**
 * Agent vision attachment thumbnail with on-demand URL refresh and lightbox preview.
 */
import { Image } from 'antd'
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  resolveAgentAttachmentUrl,
  resolveAgentAttachmentUrls,
  type AgentAttachmentMeta,
} from '@/api/agent'

type AgentAttachmentImageProps = {
  workspaceId: string | undefined
  attachment: AgentAttachmentMeta
  alt: string
  rootClassName?: string
  className?: string
  preview?: boolean
}

/** Load one agent attachment image, refreshing expired download URLs via API. */
export function AgentAttachmentImage({
  workspaceId,
  attachment,
  alt,
  rootClassName,
  className,
  preview = true,
}: AgentAttachmentImageProps) {
  const [src, setSrc] = useState<string | undefined>(() =>
    resolveAgentAttachmentUrl(attachment.download_url),
  )
  const retriedRef = useRef(false)

  const refreshUrl = useCallback(async () => {
    if (!workspaceId || !attachment.object_key) {
      setSrc(resolveAgentAttachmentUrl(attachment.download_url))
      return
    }
    try {
      const rows = await resolveAgentAttachmentUrls(workspaceId, [attachment.object_key])
      const next = rows.find((row) => row.object_key === attachment.object_key)?.download_url
      if (next) {
        setSrc(resolveAgentAttachmentUrl(next))
        return
      }
    } catch {
      // Fall back to the persisted URL when refresh fails.
    }
    setSrc(resolveAgentAttachmentUrl(attachment.download_url))
  }, [attachment.download_url, attachment.object_key, workspaceId])

  useEffect(() => {
    retriedRef.current = false
    void refreshUrl()
  }, [refreshUrl])

  const handleError = useCallback(() => {
    if (retriedRef.current) return
    retriedRef.current = true
    void refreshUrl()
  }, [refreshUrl])

  if (!src) return null

  if (!preview) {
    return (
      <img
        className={className}
        src={src}
        alt={alt}
        onError={handleError}
      />
    )
  }

  return (
    <Image
      rootClassName={rootClassName}
      className={className}
      src={src}
      alt={alt}
      preview={{ src }}
      onError={handleError}
    />
  )
}
