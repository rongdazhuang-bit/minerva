/** Single-step create form inside the fullscreen modal wizard shell. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Form, Space, Typography, message } from 'antd'
import { useTranslation } from 'react-i18next'
import { useAuth } from '@/app/AuthContext'
import { createGraphKb } from '@/features/graph-kb/api/graphKb'
import { GraphKbMetaFields } from '@/features/graph-kb/shared/GraphKbMetaFields'
import {
  ENGINE_LIGHTRAG,
  PERMISSION_ONLY_ME,
  listWorkspaceMemberOptions,
  type GraphKbFormValues,
} from '@/features/graph-kb/shared/graphKbForm'
import './GraphKbCreateWizard.css'

export type GraphKbCreateWizardProps = {
  onCancel: () => void
  onSuccess: (graphId: string) => void
}

/** Renders the graph KB create form with header, scroll body, and footer actions. */
export function GraphKbCreateWizard({ onCancel, onSuccess }: GraphKbCreateWizardProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { workspaceId } = useAuth()
  const [form] = Form.useForm<GraphKbFormValues>()
  const permission = Form.useWatch('permission', form)

  const usersQ = useQuery({
    queryKey: ['graph-kb-members', workspaceId],
    queryFn: () => listWorkspaceMemberOptions(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const createM = useMutation({
    mutationFn: (values: GraphKbFormValues) =>
      createGraphKb(workspaceId!, {
        name: values.name.trim(),
        description: values.description?.trim() || null,
        engine: values.engine,
        permission: values.permission,
        member_user_ids:
          values.permission === 'partial_members' ? (values.member_user_ids ?? []) : [],
      }),
    onSuccess: (row) => {
      message.success(t('graphKb.create.success'))
      void queryClient.invalidateQueries({ queryKey: ['graph-kbs', workspaceId] })
      onSuccess(row.id)
    },
    onError: (err: Error) => message.error(err.message),
  })

  if (!workspaceId) {
    return null
  }

  return (
    <Form
      form={form}
      layout="vertical"
      className="minerva-graph-kb-create-wizard"
      initialValues={{ engine: ENGINE_LIGHTRAG, permission: PERMISSION_ONLY_ME }}
      onFinish={(values) => createM.mutate(values)}
    >
      <div className="minerva-graph-kb-create-wizard__header">
        <Typography.Title level={4}>{t('graphKb.page.create')}</Typography.Title>
      </div>

      <div className="minerva-graph-kb-create-wizard__body minerva-scrollbar-thin">
        <div className="minerva-graph-kb-create-wizard__body-inner">
          <GraphKbMetaFields
            usersLoading={usersQ.isLoading}
            userOptions={usersQ.data ?? []}
            permission={permission}
          />
        </div>
      </div>

      <div className="minerva-graph-kb-create-wizard__footer">
        <Button onClick={onCancel}>{t('common.cancel')}</Button>
        <Space>
          <Button type="primary" htmlType="submit" loading={createM.isPending}>
            {t('graphKb.create.submit')}
          </Button>
        </Space>
      </div>
    </Form>
  )
}
