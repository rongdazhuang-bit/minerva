/** Graph settings: mutable name, ACL, members, and models; engine is read-only. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Empty, Form, Spin, message } from 'antd'
import { useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { listModelProviders } from '@/api/modelProviders'
import { useAuth } from '@/app/AuthContext'
import { getGraphKb, patchGraphKb } from '@/features/graph-kb/api/graphKb'
import { GraphKbMetaFields } from '@/features/graph-kb/shared/GraphKbMetaFields'
import {
  listWorkspaceMemberOptions,
  parseModelKey,
  toModelKey,
  type GraphKbFormValues,
} from '@/features/graph-kb/shared/graphKbForm'
import './GraphKbSettingsPage.css'

/** Settings tab: PATCH name/description/permission/members/models; engine disabled. */
export function GraphKbSettingsPage() {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const { graphId = '' } = useParams()
  const queryClient = useQueryClient()
  const [form] = Form.useForm<GraphKbFormValues>()
  const permission = Form.useWatch('permission', form)

  const detailQ = useQuery({
    queryKey: ['graph-kb-detail', workspaceId, graphId],
    queryFn: () => getGraphKb(workspaceId!, graphId),
    enabled: Boolean(workspaceId && graphId),
  })

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

  useEffect(() => {
    const row = detailQ.data
    if (!row) return
    form.setFieldsValue({
      name: row.name,
      description: row.description ?? undefined,
      engine: row.engine,
      permission: row.permission,
      member_user_ids: row.member_user_ids,
      llm_model_key: toModelKey(row.llm_model_provider, row.llm_model),
      embedding_model_key: toModelKey(row.embedding_model_provider, row.embedding_model),
    })
  }, [form, detailQ.data])

  const saveM = useMutation({
    mutationFn: (values: GraphKbFormValues) => {
      const llm = parseModelKey(values.llm_model_key)
      const embedding = parseModelKey(values.embedding_model_key)
      return patchGraphKb(workspaceId!, graphId, {
        name: values.name.trim(),
        description: values.description?.trim() || null,
        permission: values.permission,
        llm_model: llm.model,
        llm_model_provider: llm.provider,
        embedding_model: embedding.model,
        embedding_model_provider: embedding.provider,
        member_user_ids: values.permission === 'partial_members' ? (values.member_user_ids ?? []) : [],
      })
    },
    onSuccess: () => {
      message.success(t('graphKb.settings.saved'))
      void queryClient.invalidateQueries({ queryKey: ['graph-kb-detail', workspaceId, graphId] })
      void queryClient.invalidateQueries({ queryKey: ['graph-kbs', workspaceId] })
    },
    onError: (err: Error) => message.error(err.message),
  })

  if (!workspaceId) {
    return <Empty description={t('settings.ocrNoWorkspace')} style={{ color: 'var(--minerva-ink)' }} />
  }

  return (
    <Spin spinning={detailQ.isLoading}>
      <div className="minerva-graph-kb-settings-page minerva-scrollbar-thin">
        <Form form={form} layout="vertical" onFinish={(values) => saveM.mutate(values)}>
          <GraphKbMetaFields
            engineDisabled
            modelsLoading={modelsQ.isLoading}
            usersLoading={usersQ.isLoading}
            chatOptions={chatOptions}
            embeddingOptions={embeddingOptions}
            userOptions={usersQ.data ?? []}
            permission={permission}
          />
          <div className="minerva-graph-kb-settings-page__actions">
            <Button type="primary" htmlType="submit" loading={saveM.isPending}>
              {t('common.save')}
            </Button>
          </div>
        </Form>
      </div>
    </Spin>
  )
}
