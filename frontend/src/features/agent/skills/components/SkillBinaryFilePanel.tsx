/**
 * Read-only panel for non-text skill files: metadata, download, delete, and replace upload.
 */
import { DeleteOutlined, DownloadOutlined, UploadOutlined } from '@ant-design/icons'
import { Button, Descriptions, Popconfirm, Space, Typography, Upload } from 'antd'
import type { UploadProps } from 'antd/es/upload/interface'
import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  deleteSkillPath,
  downloadSkillFile,
  uploadSkillFile,
} from '@/api/agentSkillsMgmt'
import { showAppError, useAppMessage } from '@/app/useAppMessage'

const { Text } = Typography

type SkillBinaryFilePanelProps = {
  /** Tenant workspace id for skills-mgmt API calls. */
  workspaceId: string
  /** Relative path of the selected file within the skill package. */
  path: string
  /** File size in bytes from the tree node, when known. */
  size?: number | null
  /** When false, hide delete and upload-replace actions. */
  canManage: boolean
  /** Called after a successful delete or replace so the parent can refresh the tree. */
  onChanged: () => void
}

/**
 * Formats a byte count for display in the binary file panel.
 */
function formatFileSize(bytes: number | null | undefined): string {
  if (bytes == null) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/**
 * Parent directory path for uploadSkillFile (skill-relative, may be empty at skill root).
 */
function parentDirPath(filePath: string): string {
  const idx = filePath.lastIndexOf('/')
  return idx >= 0 ? filePath.slice(0, idx) : ''
}

/**
 * Shows binary file metadata and download / delete / replace actions (manage-gated).
 */
export function SkillBinaryFilePanel({
  workspaceId,
  path,
  size,
  canManage,
  onChanged,
}: SkillBinaryFilePanelProps) {
  const { t } = useTranslation()
  const messageApi = useAppMessage()
  const [downloading, setDownloading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const fileName = path.slice(path.lastIndexOf('/') + 1)

  const handleDownload = useCallback(async () => {
    setDownloading(true)
    try {
      const blob = await downloadSkillFile(workspaceId, path)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = fileName
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      showAppError(messageApi, t, e)
    } finally {
      setDownloading(false)
    }
  }, [workspaceId, path, fileName, messageApi, t])

  const handleDelete = useCallback(async () => {
    try {
      await deleteSkillPath(workspaceId, path)
      void messageApi.success(
        t('agents.skills.deleteFileSuccess', { defaultValue: '文件已删除' }),
      )
      onChanged()
    } catch (e) {
      showAppError(messageApi, t, e)
    }
  }, [workspaceId, path, messageApi, t, onChanged])

  const handleUpload = useCallback(
    async (file: File) => {
      setUploading(true)
      try {
        await uploadSkillFile(workspaceId, parentDirPath(path), file)
        void messageApi.success(
          t('agents.skills.replaceSuccess', { defaultValue: '文件已替换' }),
        )
        onChanged()
      } catch (e) {
        showAppError(messageApi, t, e)
      } finally {
        setUploading(false)
      }
    },
    [workspaceId, path, messageApi, t, onChanged],
  )

  const uploadProps: UploadProps = {
    showUploadList: false,
    disabled: !canManage || uploading,
    beforeUpload: (file) => {
      void handleUpload(file)
      return false
    },
  }

  return (
    <div className="minerva-agent-skills-page__binary-panel">
      <Descriptions column={1} size="small" bordered>
        <Descriptions.Item
          label={t('agents.skills.fileName', { defaultValue: '文件名' })}
        >
          <Text code>{fileName}</Text>
        </Descriptions.Item>
        <Descriptions.Item label={t('agents.skills.filePath', { defaultValue: '路径' })}>
          <Text type="secondary">{path}</Text>
        </Descriptions.Item>
        <Descriptions.Item label={t('agents.skills.fileSize', { defaultValue: '大小' })}>
          {formatFileSize(size)}
        </Descriptions.Item>
      </Descriptions>
      <Space wrap style={{ marginTop: 24 }}>
        <Button
          icon={<DownloadOutlined />}
          loading={downloading}
          onClick={() => void handleDownload()}
        >
          {t('agents.skills.download', { defaultValue: '下载' })}
        </Button>
        {canManage ? (
          <>
            <Upload {...uploadProps}>
              <Button icon={<UploadOutlined />} loading={uploading}>
                {t('agents.skills.replace', { defaultValue: '上传替换' })}
              </Button>
            </Upload>
            <Popconfirm
              title={t('agents.skills.deleteFileConfirm', {
                defaultValue: '确定删除该文件？此操作不可恢复。',
              })}
              onConfirm={() => void handleDelete()}
            >
              <Button danger icon={<DeleteOutlined />}>
                {t('agents.skills.deleteFile', { defaultValue: '删除' })}
              </Button>
            </Popconfirm>
          </>
        ) : null}
      </Space>
    </div>
  )
}
