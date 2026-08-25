/** Graph settings: mutable name, ACL, and members; engine is read-only. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Empty, Form, Spin, message } from 'antd'
import { useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '@/app/AuthContext'
import { useGraphKbId } from '@/features/graph-kb/shared/GraphKbContext'
import { getGraphKb, patchGraphKb } from '@/features/graph-kb/api/graphKb'
import { GraphKbMetaFields } from '@/features/graph-kb/shared/GraphKbMetaFields'
import {
  listWorkspaceMemberOptions,
  mergeMemberSelectOptions,
  type GraphKbFormValues,
} from '@/features/graph-kb/shared/graphKbForm'
import './GraphKbSettingsPage.css'

/** Settings tab: PATCH name/description/permission/members; engine disabled. */
export function GraphKbSettingsPage() {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const graphId = useGraphKbId()
  const queryClient = useQueryClient()
  const [form] = Form.useForm<GraphKbFormValues>()
  const permission = Form.useWatch('permission', form)

  const detailQ = useQuery({
    queryKey: ['graph-kb-detail', workspaceId, graphId],
    queryFn: () => getGraphKb(workspaceId!, graphId),
    enabled: Boolean(workspaceId && graphId),
  })

  const usersQ = useQuery({
    queryKey: ['graph-kb-members', workspaceId],
    queryFn: () => listWorkspaceMemberOptions(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const userOptions = useMemo(
    () =>
      mergeMemberSelectOptions(
        usersQ.data ?? [],
        detailQ.data?.member_user_ids,
        t('graphKb.field.unknownUser'),
      ),
    [detailQ.data?.member_user_ids, t, usersQ.data],
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
    })
  }, [form, detailQ.data])

  const saveM = useMutation({
    mutationFn: (values: GraphKbFormValues) =>
      patchGraphKb(workspaceId!, graphId, {
        name: values.name.trim(),
        description: values.description?.trim() || null,
        permission: values.permission,
        member_user_ids:
          values.permission === 'partial_members' ? (values.member_user_ids ?? []) : [],
      }),
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
            usersLoading={usersQ.isLoading}
            userOptions={userOptions}
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
