/** Shared create/settings fields: engine, permission, members, and models. */

import { Form, Input, Select } from 'antd'
import { useTranslation } from 'react-i18next'
import {
  ENGINE_GRAPHRAG,
  ENGINE_LIGHTRAG,
  PERMISSION_ALL_TEAM_MEMBERS,
  PERMISSION_ONLY_ME,
  PERMISSION_PARTIAL_MEMBERS,
  type SelectOption,
} from '@/features/graph-kb/shared/graphKbForm'

type GraphKbMetaFieldsProps = {
  /** When true, engine Select is locked (settings page). */
  engineDisabled?: boolean
  modelsLoading?: boolean
  usersLoading?: boolean
  chatOptions: SelectOption[]
  embeddingOptions: SelectOption[]
  userOptions: SelectOption[]
  /** Current permission value; members Select shows only for ``partial_members``. */
  permission?: string
}

/** Name, description, engine, ACL, and model Selects shared by create and settings. */
export function GraphKbMetaFields({
  engineDisabled = false,
  modelsLoading = false,
  usersLoading = false,
  chatOptions,
  embeddingOptions,
  userOptions,
  permission,
}: GraphKbMetaFieldsProps) {
  const { t } = useTranslation()

  return (
    <>
      <Form.Item
        name="name"
        label={t('graphKb.field.name')}
        rules={[{ required: true, message: t('graphKb.field.nameRequired') }]}
      >
        <Input allowClear placeholder={t('graphKb.field.namePh')} />
      </Form.Item>
      <Form.Item name="description" label={t('graphKb.field.description')}>
        <Input.TextArea allowClear rows={2} placeholder={t('graphKb.field.descriptionPh')} />
      </Form.Item>
      <Form.Item
        name="engine"
        label={t('graphKb.field.engine')}
        rules={[{ required: true, message: t('graphKb.field.engineRequired') }]}
        extra={engineDisabled ? t('graphKb.field.engineLocked') : undefined}
      >
        <Select
          disabled={engineDisabled}
          placeholder={t('graphKb.field.enginePh')}
          options={[
            { value: ENGINE_GRAPHRAG, label: t('graphKb.engine.graphrag') },
            { value: ENGINE_LIGHTRAG, label: t('graphKb.engine.lightrag') },
          ]}
        />
      </Form.Item>
      <Form.Item
        name="permission"
        label={t('graphKb.field.permission')}
        rules={[{ required: true, message: t('graphKb.field.permissionRequired') }]}
      >
        <Select
          placeholder={t('graphKb.field.permissionPh')}
          options={[
            { value: PERMISSION_ONLY_ME, label: t('graphKb.permission.only_me') },
            { value: PERMISSION_PARTIAL_MEMBERS, label: t('graphKb.permission.partial_members') },
            { value: PERMISSION_ALL_TEAM_MEMBERS, label: t('graphKb.permission.all_team_members') },
          ]}
        />
      </Form.Item>
      {permission === PERMISSION_PARTIAL_MEMBERS ? (
        <Form.Item name="member_user_ids" label={t('graphKb.field.members')}>
          <Select
            mode="multiple"
            allowClear
            showSearch
            optionFilterProp="label"
            loading={usersLoading}
            placeholder={t('graphKb.field.membersPh')}
            options={userOptions}
          />
        </Form.Item>
      ) : null}
      <Form.Item name="llm_model_key" label={t('graphKb.field.llm')}>
        <Select
          allowClear
          showSearch
          optionFilterProp="label"
          loading={modelsLoading}
          placeholder={t('graphKb.field.llmPh')}
          options={chatOptions}
        />
      </Form.Item>
      <Form.Item name="embedding_model_key" label={t('graphKb.field.embedding')}>
        <Select
          allowClear
          showSearch
          optionFilterProp="label"
          loading={modelsLoading}
          placeholder={t('graphKb.field.embeddingPh')}
          options={embeddingOptions}
        />
      </Form.Item>
    </>
  )
}
