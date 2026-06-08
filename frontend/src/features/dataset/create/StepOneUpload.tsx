/** Step 1 — upload source files for dataset creation. */

import { InboxOutlined } from '@ant-design/icons'
import { Alert, Form, Input, Upload, message } from 'antd'
import type { FormInstance } from 'antd'
import type { UploadFile, UploadProps } from 'antd/es/upload/interface'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { uploadDatasetFile, type DatasetUploadOut } from '@/features/dataset/api/datasets'
import {
  DATASET_UPLOAD_ACCEPT,
  isDatasetAllowedExtension,
} from '@/features/dataset/shared/allowedExtensions'
import './StepOneUpload.css'

export type UploadedDatasetFile = DatasetUploadOut & { uid: string }

export type StepOneUploadProps = {
  workspaceId: string
  value: UploadedDatasetFile[]
  onChange: (files: UploadedDatasetFile[]) => void
  /** When set (create flow), renders name/description fields above the uploader. */
  form?: FormInstance
}

const MAX_FILES = 5
const MAX_MB = 100

/** Map persisted uploads to Ant Design file list entries. */
function toDoneFileList(items: UploadedDatasetFile[]): UploadFile[] {
  return items.map((item) => ({
    uid: item.uid,
    name: item.name,
    status: 'done' as const,
    size: item.size,
  }))
}

/** Upload dragger for dataset source files. */
export function StepOneUpload({ workspaceId, value, onChange, form }: StepOneUploadProps) {
  const { t } = useTranslation()
  const valueRef = useRef(value)
  valueRef.current = value

  const [fileList, setFileList] = useState<UploadFile[]>(() => toDoneFileList(value))

  useEffect(() => {
    setFileList((prev) => {
      const inFlight = prev.filter((file) => file.status === 'uploading' || file.status === 'error')
      return [...inFlight, ...toDoneFileList(value)]
    })
  }, [value])

  const handleUploadChange = useCallback<NonNullable<UploadProps['onChange']>>(({ fileList: next }) => {
    setFileList(next)
  }, [])

  const customRequest = useCallback<NonNullable<UploadProps['customRequest']>>(
    async (options) => {
      const uploadFile = options.file as UploadFile
      const uid = uploadFile.uid
      const raw = uploadFile.originFileObj ?? (options.file as File)

      setFileList((prev) =>
        prev.map((file) =>
          file.uid === uid ? { ...file, status: 'uploading', percent: file.percent ?? 0 } : file,
        ),
      )

      try {
        const uploaded = await uploadDatasetFile(workspaceId, raw, (percent) => {
          options.onProgress?.({ percent })
          setFileList((prev) =>
            prev.map((file) => (file.uid === uid ? { ...file, status: 'uploading', percent } : file)),
          )
        })

        const nextItem: UploadedDatasetFile = { ...uploaded, uid: uploaded.id }
        onChange([...valueRef.current, nextItem])

        setFileList((prev) => {
          const rest = prev.filter((file) => file.uid !== uid)
          return [
            ...rest,
            {
              uid: uploaded.id,
              name: uploaded.name,
              status: 'done' as const,
              size: uploaded.size,
              percent: 100,
            },
          ]
        })
        options.onSuccess?.(uploaded)
      } catch (err) {
        setFileList((prev) =>
          prev.map((file) => (file.uid === uid ? { ...file, status: 'error' } : file)),
        )
        options.onError?.(err instanceof Error ? err : new Error(String(err)))
      }
    },
    [onChange, workspaceId],
  )

  const uploadBlock = (
    <>
      <Alert
        type="info"
        showIcon
        message={t('dataset.create.uploadHint', {
          maxFiles: MAX_FILES,
          maxMb: MAX_MB,
        })}
        style={{ marginBottom: 16 }}
      />
      <Upload.Dragger
        multiple
        accept={DATASET_UPLOAD_ACCEPT}
        fileList={fileList}
        customRequest={customRequest}
        onChange={handleUploadChange}
        showUploadList={{ showRemoveIcon: true }}
        progress={{ strokeWidth: 3, showInfo: true }}
        onRemove={(file) => {
          onChange(valueRef.current.filter((item) => item.uid !== file.uid))
          setFileList((prev) => prev.filter((item) => item.uid !== file.uid))
          return true
        }}
        beforeUpload={(file, batch) => {
          if (!isDatasetAllowedExtension(file.name)) {
            message.error(t('dataset.create.uploadInvalidExt'))
            return Upload.LIST_IGNORE
          }
          const doneCount = valueRef.current.length
          const uploadingCount = fileList.filter((item) => item.status === 'uploading').length
          if (doneCount + uploadingCount + batch.length > MAX_FILES) {
            return Upload.LIST_IGNORE
          }
          if (file.size > MAX_MB * 1024 * 1024) {
            return Upload.LIST_IGNORE
          }
          return true
        }}
      >
        <p className="ant-upload-drag-icon">
          <InboxOutlined />
        </p>
        <p className="ant-upload-text">{t('dataset.create.uploadTitle')}</p>
        <p className="ant-upload-hint">{t('dataset.create.uploadDesc')}</p>
      </Upload.Dragger>
    </>
  )

  return (
    <div className="minerva-dataset-step-one">
      <div className="minerva-dataset-step-one__inner">
        {form ? (
          <Form form={form} layout="vertical">
            <Form.Item
              name="name"
              label={t('dataset.create.field.name')}
              rules={[{ required: true, message: t('dataset.create.field.nameRequired') }]}
            >
              <Input allowClear placeholder={t('dataset.create.field.namePh')} />
            </Form.Item>
            <Form.Item name="description" label={t('dataset.create.field.description')}>
              <Input.TextArea allowClear rows={2} />
            </Form.Item>
            {uploadBlock}
          </Form>
        ) : (
          uploadBlock
        )}
      </div>
    </div>
  )
}
