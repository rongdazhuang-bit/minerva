/** Create an empty graph knowledge base, then open its documents tab. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Card, Empty, Form, Space, Typography, message } from 'antd'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { listModelProviders } from '@/api/modelProviders'
import { useAuth } from '@/app/AuthContext'
import { createGraphKb } from '@/features/graph-kb/api/graphKb'
import { GraphKbMetaFields } from '@/features/graph-kb/shared/GraphKbMetaFields'
import {
  ENGINE_LIGHTRAG,
  PERMISSION_ONLY_ME,
  parseModelKey,
  listWorkspaceMemberOptions,
  type GraphKbFormValues,
} from '@/features/graph-kb/shared/graphKbForm'
import './GraphKbCreatePage.css'

/** Standalone create page at `/app/graph-kb/create`. */
export function GraphKbCreatePage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { workspaceId } = useAuth()
  const [form] = Form.useForm<GraphKbFormValues>()
  const permission = Form.useWatch('permission', form)

  const modelsQ = useQuery({
    queryKey: ['model-providers', workspaceId],
    queryFn: () => listModelProviders(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const usersQ = useQuery({
    queryKey: ['graph-kb-members', workspaceId],
    queryFn: () => listWorkspaceMemberOptions(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const chatOptions = useMemo(
    () =>
      (modelsQ.data ?? [])
        .filter((item) => item.enabled && item.tags.includes('CHAT'))
        .map((item) => ({
          value: `${item.provider_name}::${item.model_name}`,
          label: `${item.provider_name} / ${item.model_name}`,
        })),
    [modelsQ.data],
  )

  const embeddingOptions = useMemo(
    () =>
      (modelsQ.data ?? [])
        .filter((item) => item.enabled && item.tags.includes('EMBEDDINGS'))
        .map((item) => ({
          value: `${item.provider_name}::${item.model_name}`,
          label: `${item.provider_name} / ${item.model_name}`,
        })),
    [modelsQ.data],
  )

  const createM = useMutation({
    mutationFn: (values: GraphKbFormValues) => {
      const llm = parseModelKey(values.llm_model_key)
      const embedding = parseModelKey(values.embedding_model_key)
      return createGraphKb(workspaceId!, {
        name: values.name.trim(),
        description: values.description?.trim() || null,
        engine: values.engine,
        permission: values.permission,
        llm_model: llm.model,
        llm_model_provider: llm.provider,
        embedding_model: embedding.model,
        embedding_model_provider: embedding.provider,
        member_user_ids: values.permission === 'partial_members' ? (values.member_user_ids ?? []) : [],
      })
    },
    onSuccess: (row) => {
      message.success(t('graphKb.create.success'))
      void queryClient.invalidateQueries({ queryKey: ['graph-kbs', workspaceId] })
      navigate(`/app/graph-kb/${row.id}/documents`)
    },
    onError: (err: Error) => message.error(err.message),
  })

  if (!workspaceId) {
    return (
      <div className="minerva-page-fill">
        <Empty description={t('settings.ocrNoWorkspace')} style={{ color: 'var(--minerva-ink)' }} />
      </div>
    )
  }

  return (
    <div className="minerva-page-fill">
      <Card variant="borderless" className="minerva-page-shell-card">
        <div className="minerva-graph-kb-create-page">
          <Typography.Title level={4}>{t('graphKb.page.create')}</Typography.Title>
          <Form
            form={form}
            layout="vertical"
            initialValues={{ engine: ENGINE_LIGHTRAG, permission: PERMISSION_ONLY_ME }}
            onFinish={(values) => createM.mutate(values)}
          >
            <GraphKbMetaFields
              modelsLoading={modelsQ.isLoading}
              usersLoading={usersQ.isLoading}
              chatOptions={chatOptions}
              embeddingOptions={embeddingOptions}
              userOptions={usersQ.data ?? []}
              permission={permission}
            />
            <div className="minerva-graph-kb-create-page__actions">
              <Space>
                <Button onClick={() => navigate('/app/graph-kb')}>{t('common.cancel')}</Button>
                <Button type="primary" htmlType="submit" loading={createM.isPending}>
                  {t('graphKb.create.submit')}
                </Button>
              </Space>
            </div>
          </Form>
        </div>
      </Card>
    </div>
  )
}
