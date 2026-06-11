import { Alert, Button, Drawer, Form, Input, Radio, Select, Space, TreeSelect } from 'antd'
import type { TreeSelectProps } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type {
  SysUserCreateBody,
  SysUserDepartmentNode,
  SysUserRoleOption,
} from '@/api/users'
import { listUserAssignableRoles, listUserDepartmentTree } from '@/api/users'

/** Form values for create/edit user drawer. */
export type UserFormValues = {
  email: string
  password?: string
  nickname: string
  phone?: string | null
  status?: boolean
  remark?: string | null
  membership_role: string
  department_item_id?: string | null
  role_ids?: string[]
}

type Props = {
  open: boolean
  title: string
  submitting: boolean
  mode: 'create' | 'edit'
  workspaceId: string | null
  initial?: UserFormValues | null
  onClose: () => void
  onSubmit: (values: SysUserCreateBody | Record<string, unknown>) => Promise<void>
}

/** Build Ant Design tree nodes from department API tree. */
function buildDepartmentTreeData(
  nodes: SysUserDepartmentNode[],
): NonNullable<TreeSelectProps['treeData']> {
  return nodes.map((n) => ({
    title: `${n.code} — ${n.name}`,
    value: n.id,
    key: n.id,
    children:
      n.children?.length > 0
        ? buildDepartmentTreeData(n.children)
        : undefined,
  }))
}

/** Right drawer for creating or editing a workspace member. */
export function UserFormDrawer({
  open,
  title,
  submitting,
  mode,
  workspaceId,
  initial,
  onClose,
  onSubmit,
}: Props) {
  const { t } = useTranslation()
  const [form] = Form.useForm<UserFormValues>()
  const [departments, setDepartments] = useState<SysUserDepartmentNode[]>([])
  const [roles, setRoles] = useState<SysUserRoleOption[]>([])
  const [metaLoading, setMetaLoading] = useState(false)

  const departmentTree = useMemo(
    () => buildDepartmentTreeData(departments),
    [departments],
  )

  useEffect(() => {
    if (!open || !workspaceId) return
    setMetaLoading(true)
    void Promise.all([
      listUserDepartmentTree(workspaceId),
      listUserAssignableRoles(workspaceId),
    ])
      .then(([deptRows, roleRows]) => {
        setDepartments(deptRows)
        setRoles(roleRows)
      })
      .finally(() => setMetaLoading(false))
  }, [open, workspaceId])

  useEffect(() => {
    if (!open) return
    form.setFieldsValue({
      email: initial?.email ?? '',
      password: '',
      nickname: initial?.nickname ?? '',
      phone: initial?.phone ?? null,
      status: initial?.status ?? true,
      remark: initial?.remark ?? null,
      membership_role: initial?.membership_role ?? 'member',
      department_item_id: initial?.department_item_id ?? null,
      role_ids: initial?.role_ids ?? [],
    })
  }, [open, initial, form])

  const handleFinish = useCallback(
    async (values: UserFormValues) => {
      if (mode === 'create') {
        await onSubmit({
          email: values.email.trim(),
          password: values.password ?? '',
          nickname: values.nickname.trim(),
          phone: values.phone?.trim() || null,
          status: values.status ?? true,
          remark: values.remark?.trim() || null,
          membership_role: values.membership_role,
          department_item_id: values.department_item_id ?? null,
          role_ids: values.role_ids ?? [],
        })
        return
      }
      const patch: Record<string, unknown> = {
        nickname: values.nickname.trim(),
        phone: values.phone?.trim() || null,
        status: values.status ?? true,
        remark: values.remark?.trim() || null,
        membership_role: values.membership_role,
        department_item_id: values.department_item_id ?? null,
        role_ids: values.role_ids ?? [],
      }
      if (values.password?.trim()) {
        patch.password = values.password.trim()
      }
      await onSubmit(patch)
    },
    [mode, onSubmit],
  )

  return (
    <Drawer
      title={title}
      width={520}
      open={open}
      destroyOnClose
      onClose={onClose}
      classNames={{ body: 'minerva-scrollbar-styled' }}
      footer={
        <Space style={{ float: 'right' }}>
          <Button onClick={onClose}>{t('common.cancel')}</Button>
          <Button type="primary" loading={submitting} onClick={() => form.submit()}>
            {t('common.save')}
          </Button>
        </Space>
      }
    >
      {departments.length === 0 && !metaLoading ? (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={t('users.departmentDictMissing')}
        />
      ) : null}
      <Form form={form} layout="vertical" onFinish={handleFinish}>
        <Form.Item
          name="email"
          label={t('users.email')}
          rules={
            mode === 'create'
              ? [
                  { required: true, message: t('users.emailRequired') },
                  { type: 'email', message: t('users.emailInvalid') },
                ]
              : undefined
          }
        >
          <Input
            allowClear
            disabled={mode === 'edit'}
            placeholder={t('users.emailPlaceholder')}
          />
        </Form.Item>
        <Form.Item
          name="password"
          label={t('users.password')}
          rules={
            mode === 'create'
              ? [
                  { required: true, message: t('users.passwordRequired') },
                  { min: 8, message: t('users.passwordMin') },
                ]
              : [
                  {
                    validator: (_r, v: string | undefined) => {
                      if (!v || !v.trim()) return Promise.resolve()
                      if (v.length < 8) {
                        return Promise.reject(new Error(t('users.passwordMin')))
                      }
                      return Promise.resolve()
                    },
                  },
                ]
          }
        >
          <Input.Password
            allowClear
            placeholder={
              mode === 'edit' ? t('users.passwordEditPlaceholder') : t('users.passwordPlaceholder')
            }
          />
        </Form.Item>
        <Form.Item
          name="nickname"
          label={t('users.nickname')}
          rules={[{ required: true, message: t('users.nicknameRequired') }]}
        >
          <Input allowClear placeholder={t('users.nicknamePlaceholder')} />
        </Form.Item>
        <Form.Item name="phone" label={t('users.phone')}>
          <Input allowClear placeholder={t('users.phonePlaceholder')} />
        </Form.Item>
        <Form.Item name="status" label={t('users.status')} initialValue>
          <Radio.Group>
            <Radio value>{t('users.statusNormal')}</Radio>
            <Radio value={false}>{t('users.statusDisabled')}</Radio>
          </Radio.Group>
        </Form.Item>
        <Form.Item
          name="membership_role"
          label={t('users.membershipRole')}
          rules={[{ required: true, message: t('users.membershipRoleRequired') }]}
        >
          <Select
            allowClear={false}
            options={[
              { value: 'owner', label: t('users.membershipOwner') },
              { value: 'admin', label: t('users.membershipAdmin') },
              { value: 'member', label: t('users.membershipMember') },
            ]}
          />
        </Form.Item>
        <Form.Item name="department_item_id" label={t('users.department')}>
          <TreeSelect
            allowClear
            showSearch
            treeDefaultExpandAll
            loading={metaLoading}
            placeholder={t('users.departmentPlaceholder')}
            treeData={departmentTree}
            treeNodeFilterProp="title"
          />
        </Form.Item>
        <Form.Item name="role_ids" label={t('users.roles')}>
          <Select
            allowClear
            mode="multiple"
            loading={metaLoading}
            placeholder={t('users.rolesPlaceholder')}
            options={roles.map((r) => ({
              value: r.id,
              label: r.role_name,
            }))}
          />
        </Form.Item>
        <Form.Item name="remark" label={t('users.remark')}>
          <Input.TextArea
            allowClear
            rows={3}
            placeholder={t('users.remarkPlaceholder')}
            classNames={{ textarea: 'minerva-scrollbar-styled' }}
          />
        </Form.Item>
      </Form>
    </Drawer>
  )
}
