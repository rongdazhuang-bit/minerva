import { Alert, Button, Drawer, Form, Input, Radio, Select, Space, Tag, TreeSelect } from 'antd'
import type { TreeSelectProps } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type {
  SysUserCapabilities,
  SysUserCreateBody,
  SysUserDepartmentNode,
  SysUserListCapabilities,
  SysUserRoleOption,
} from '@/api/users'
import {
  getUserCapabilities,
  listUserAssignableRoles,
  listUserDepartmentTree,
} from '@/api/users'

/** Form values for create/edit user drawer. */
export type UserFormValues = {
  email: string
  password?: string
  nickname: string
  phone?: string | null
  status?: boolean
  remark?: string | null
  membership_role: string
  tenant_admin_role?: 'admin' | 'member'
  department_item_id?: string | null
  role_ids?: string[]
  tenant_id?: string
  workspace_id?: string
}

/** Read-only scope shown when editing a user. */
export type UserScope = {
  tenant_id: string
  tenant_name: string
  workspace_id: string
  workspace_name: string
}

type SubmitContext = {
  targetWorkspaceId: string
  effectiveTenantId: string | null
}

type Props = {
  open: boolean
  title: string
  submitting: boolean
  mode: 'create' | 'edit'
  listCapabilities: SysUserListCapabilities | null
  pageWorkspaceId: string | null
  initial?: UserFormValues | null
  initialScope?: UserScope | null
  tenants?: { id: string; name: string }[]
  workspaces?: { id: string; name: string }[]
  workspacesLoading?: boolean
  onTenantChange?: (tenantId: string) => void
  onClose: () => void
  onSubmit: (
    values: SysUserCreateBody | Record<string, unknown>,
    context: SubmitContext,
  ) => Promise<void>
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
      n.children?.length > 0 ? buildDepartmentTreeData(n.children) : undefined,
  }))
}

/** Map membership_role code to i18n label. */
function membershipRoleLabel(role: string, t: (key: string) => string): string {
  if (role === 'admin') return t('users.membershipAdmin')
  return t('users.membershipMember')
}

/** Right drawer for creating or editing a workspace member. */
export function UserFormDrawer({
  open,
  title,
  submitting,
  mode,
  listCapabilities,
  pageWorkspaceId,
  initial,
  initialScope,
  tenants = [],
  workspaces = [],
  workspacesLoading = false,
  onTenantChange,
  onClose,
  onSubmit,
}: Props) {
  const { t } = useTranslation()
  const [form] = Form.useForm<UserFormValues>()
  const [departments, setDepartments] = useState<SysUserDepartmentNode[]>([])
  const [roles, setRoles] = useState<SysUserRoleOption[]>([])
  const [formCapabilities, setFormCapabilities] = useState<SysUserCapabilities | null>(
    null,
  )
  const [metaLoading, setMetaLoading] = useState(false)

  const selectedTenantId = Form.useWatch('tenant_id', form)
  const selectedWorkspaceId = Form.useWatch('workspace_id', form)

  const showScopeOnCreate =
    mode === 'create' && listCapabilities?.can_pick_workspace === true

  const showScopeReadonlyOnEdit =
    mode === 'edit' &&
    initialScope != null &&
    listCapabilities?.can_pick_workspace === true

  const effectiveWorkspaceId = useMemo(() => {
    if (showScopeOnCreate) {
      return selectedWorkspaceId ?? null
    }
    if (showScopeReadonlyOnEdit && initialScope) {
      return initialScope.workspace_id
    }
    return pageWorkspaceId
  }, [
    showScopeOnCreate,
    showScopeReadonlyOnEdit,
    selectedWorkspaceId,
    pageWorkspaceId,
    initialScope,
  ])

  const effectiveTenantId = useMemo(() => {
    if (showScopeOnCreate) {
      return selectedTenantId ?? listCapabilities?.fixed_tenant_id ?? null
    }
    if (showScopeReadonlyOnEdit && initialScope) {
      return initialScope.tenant_id
    }
    return listCapabilities?.fixed_tenant_id ?? null
  }, [
    showScopeOnCreate,
    showScopeReadonlyOnEdit,
    selectedTenantId,
    initialScope,
    listCapabilities?.fixed_tenant_id,
  ])

  const departmentTree = useMemo(
    () => buildDepartmentTreeData(departments),
    [departments],
  )

  const membershipRoleOptions = useMemo(
    () => [
      { value: 'member', label: t('users.membershipMember') },
      { value: 'admin', label: t('users.membershipAdmin') },
    ],
    [t],
  )

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
      tenant_admin_role: initial?.tenant_admin_role ?? 'member',
      department_item_id: initial?.department_item_id ?? null,
      role_ids: initial?.role_ids ?? [],
      tenant_id:
        mode === 'edit' && initialScope
          ? initialScope.tenant_id
          : initial?.tenant_id ??
            listCapabilities?.fixed_tenant_id ??
            undefined,
      workspace_id:
        mode === 'edit' && initialScope
          ? initialScope.workspace_id
          : initial?.workspace_id ?? undefined,
    })
  }, [open, initial, initialScope, listCapabilities, form, mode])

  useEffect(() => {
    if (!showScopeOnCreate || !open) return
    if (workspaces.length === 0) {
      if (selectedWorkspaceId) {
        form.setFieldValue('workspace_id', undefined)
        form.setFieldValue('role_ids', [])
        setRoles([])
        setDepartments([])
        setFormCapabilities(null)
      }
      return
    }
    if (
      selectedWorkspaceId &&
      !workspaces.some((workspace) => workspace.id === selectedWorkspaceId)
    ) {
      form.setFieldValue('workspace_id', undefined)
      form.setFieldValue('role_ids', [])
      setRoles([])
      setDepartments([])
      setFormCapabilities(null)
      return
    }
    if (selectedWorkspaceId) return
    const preferred =
      initial?.workspace_id && workspaces.some((w) => w.id === initial.workspace_id)
        ? initial.workspace_id
        : workspaces[0]?.id
    if (preferred) {
      form.setFieldValue('workspace_id', preferred)
    }
  }, [
    showScopeOnCreate,
    open,
    selectedWorkspaceId,
    workspaces,
    initial?.workspace_id,
    form,
  ])

  useEffect(() => {
    if (!open || !effectiveWorkspaceId) return
    if (
      showScopeOnCreate &&
      workspaces.length > 0 &&
      !workspaces.some((workspace) => workspace.id === effectiveWorkspaceId)
    ) {
      return
    }
    let cancelled = false
    setMetaLoading(true)
    void Promise.all([
      getUserCapabilities(effectiveWorkspaceId),
      listUserDepartmentTree(effectiveWorkspaceId),
      listUserAssignableRoles(effectiveWorkspaceId),
    ])
      .then(([caps, deptRows, roleRows]) => {
        if (cancelled) return
        setFormCapabilities(caps)
        setDepartments(deptRows)
        setRoles(roleRows)
      })
      .finally(() => {
        if (!cancelled) setMetaLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, effectiveWorkspaceId, showScopeOnCreate, workspaces])

  const handleFinish = useCallback(
    async (values: UserFormValues) => {
      const targetWorkspaceId =
        mode === 'edit' && initialScope
          ? initialScope.workspace_id
          : (effectiveWorkspaceId ?? pageWorkspaceId)
      if (!targetWorkspaceId) return

      const membershipRole = formCapabilities?.can_edit_membership_role
        ? values.membership_role
        : (initial?.membership_role ?? 'member')

      if (mode === 'create') {
        await onSubmit(
          {
            email: values.email.trim(),
            password: values.password ?? '',
            nickname: values.nickname.trim(),
            phone: values.phone?.trim() || null,
            status: values.status ?? true,
            remark: values.remark?.trim() || null,
            membership_role: membershipRole,
            tenant_admin_role: values.tenant_admin_role,
            department_item_id: values.department_item_id ?? null,
            role_ids: values.role_ids ?? [],
          },
          { targetWorkspaceId, effectiveTenantId },
        )
        return
      }

      const patch: Record<string, unknown> = {
        nickname: values.nickname.trim(),
        phone: values.phone?.trim() || null,
        status: values.status ?? true,
        remark: values.remark?.trim() || null,
        department_item_id: values.department_item_id ?? null,
        role_ids: values.role_ids ?? [],
        tenant_admin_role: values.tenant_admin_role,
      }
      if (formCapabilities?.can_edit_membership_role) {
        patch.membership_role = membershipRole
      }
      if (values.password?.trim()) {
        patch.password = values.password.trim()
      }
      await onSubmit(patch, { targetWorkspaceId, effectiveTenantId })
    },
    [
      mode,
      onSubmit,
      effectiveWorkspaceId,
      effectiveTenantId,
      pageWorkspaceId,
      initialScope,
      formCapabilities,
      initial?.membership_role,
    ],
  )

  return (
    <Drawer
      title={title}
      width={520}
      open={open}
      destroyOnClose
      onClose={onClose}
      footer={null}
      classNames={{ body: 'minerva-scrollbar-styled' }}
      extra={
        <Space>
          <Button onClick={onClose} disabled={submitting}>
            {t('common.cancel')}
          </Button>
          <Button type="primary" loading={submitting} onClick={() => void form.submit()}>
            {t('common.save')}
          </Button>
        </Space>
      }
    >
      {departments.length === 0 && !metaLoading && !showScopeOnCreate ? (
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
        {showScopeReadonlyOnEdit && initialScope ? (
          <>
            <Form.Item name="tenant_id" label={t('users.tenant')}>
              <Select
                disabled
                options={[
                  {
                    value: initialScope.tenant_id,
                    label: initialScope.tenant_name,
                  },
                ]}
              />
            </Form.Item>
            <Form.Item name="workspace_id" label={t('users.workspace')}>
              <Select
                disabled
                options={[
                  {
                    value: initialScope.workspace_id,
                    label: initialScope.workspace_name,
                  },
                ]}
              />
            </Form.Item>
          </>
        ) : null}
        {showScopeOnCreate ? (
          <>
            {listCapabilities?.can_pick_tenant ? (
              <Form.Item
                name="tenant_id"
                label={t('users.tenant')}
                rules={[{ required: true, message: t('users.tenantPlaceholder') }]}
              >
                <Select
                  allowClear={false}
                  loading={workspacesLoading}
                  placeholder={t('users.tenantPlaceholder')}
                  options={tenants.map((row) => ({
                    value: row.id,
                    label: row.name,
                  }))}
                  onChange={(tenantId: string) => {
                    form.setFieldValue('workspace_id', undefined)
                    form.setFieldValue('role_ids', [])
                    form.setFieldValue('tenant_admin_role', 'member')
                    setDepartments([])
                    setRoles([])
                    setFormCapabilities(null)
                    void onTenantChange?.(tenantId)
                  }}
                />
              </Form.Item>
            ) : listCapabilities?.fixed_tenant_name ? (
              <Form.Item label={t('users.tenant')}>
                <Tag>{listCapabilities.fixed_tenant_name}</Tag>
              </Form.Item>
            ) : null}
            <Form.Item
              name="workspace_id"
              label={t('users.workspace')}
              rules={[{ required: true, message: t('users.workspacePlaceholder') }]}
            >
              <Select
                allowClear={false}
                loading={workspacesLoading}
                disabled={
                  workspacesLoading ||
                  (listCapabilities?.can_pick_tenant && !selectedTenantId)
                }
                placeholder={t('users.workspacePlaceholder')}
                options={workspaces.map((row) => ({
                  value: row.id,
                  label: row.name,
                }))}
                onChange={() => {
                  form.setFieldValue('role_ids', [])
                  setRoles([])
                  setDepartments([])
                  setFormCapabilities(null)
                }}
              />
            </Form.Item>
          </>
        ) : null}
        {listCapabilities?.can_edit_tenant_admin && effectiveTenantId ? (
          <Form.Item
            name="tenant_admin_role"
            label={t('users.tenantAdminRole')}
            initialValue="member"
          >
            <Select allowClear={false} options={membershipRoleOptions} />
          </Form.Item>
        ) : null}
        {formCapabilities?.can_view_membership_role ? (
          formCapabilities.can_edit_membership_role ? (
            <Form.Item
              name="membership_role"
              label={t('users.workspaceAdminRole')}
              rules={[{ required: true, message: t('users.membershipRoleRequired') }]}
            >
              <Select
                allowClear={false}
                options={formCapabilities.assignable_membership_roles.map((value) => ({
                  value,
                  label: membershipRoleLabel(value, t),
                }))}
              />
            </Form.Item>
          ) : (
            <Form.Item label={t('users.workspaceAdminRole')}>
              <Select
                disabled
                value={form.getFieldValue('membership_role') ?? initial?.membership_role ?? 'member'}
                options={membershipRoleOptions}
              />
            </Form.Item>
          )
        ) : null}
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
            disabled={!effectiveWorkspaceId}
            loading={metaLoading}
            placeholder={
              effectiveWorkspaceId
                ? t('users.rolesPlaceholder')
                : t('users.rolesSelectWorkspaceFirst')
            }
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
