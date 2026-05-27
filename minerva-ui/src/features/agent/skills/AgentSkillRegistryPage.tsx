/**
 * Edits the global skills INDEX.md registry via Monaco editor.
 */
import { ArrowLeftOutlined, SaveOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Space, Spin, Typography } from 'antd'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useBlocker, useNavigate } from 'react-router-dom'
import { readSkillFile, writeSkillFile } from '@/api/agentSkillsMgmt'
import { useAuth } from '@/app/AuthContext'
import { showAppError, useAppMessage } from '@/app/useAppMessage'
import { SkillFileEditor } from '@/features/agent/skills/components/SkillFileEditor'
import './AgentSkillsPage.css'

const INDEX_PATH = 'INDEX.md'

const { Text } = Typography

/** INDEX.md registry editor with save and unsaved navigation guard. */
export function AgentSkillRegistryPage() {
  const { t } = useTranslation()
  const messageApi = useAppMessage()
  const navigate = useNavigate()
  const { workspaceId, canManageTenantSkills } = useAuth()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [content, setContent] = useState('')
  const [savedContent, setSavedContent] = useState('')
  const confirmShownRef = useRef(false)

  const isDirty = content !== savedContent

  const loadIndex = useCallback(async () => {
    if (!workspaceId) return
    setLoading(true)
    try {
      const data = await readSkillFile(workspaceId, INDEX_PATH)
      setContent(data.content)
      setSavedContent(data.content)
    } catch (e) {
      showAppError(messageApi, t, e)
    } finally {
      setLoading(false)
    }
  }, [workspaceId, messageApi, t])

  useEffect(() => {
    void loadIndex()
  }, [loadIndex])

  useEffect(() => {
    if (!isDirty) return
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault()
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [isDirty])

  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      isDirty && currentLocation.pathname !== nextLocation.pathname,
  )

  useEffect(() => {
    if (blocker.state !== 'blocked') {
      confirmShownRef.current = false
      return
    }
    if (confirmShownRef.current) return
    confirmShownRef.current = true
    const ok = window.confirm(
      t('agents.skills.unsaved', { defaultValue: '有未保存的修改，确定离开？' }),
    )
    if (ok) blocker.proceed()
    else blocker.reset()
  }, [blocker, t])

  const handleSave = useCallback(async () => {
    if (!workspaceId || !canManageTenantSkills) return
    setSaving(true)
    try {
      await writeSkillFile(workspaceId, INDEX_PATH, content)
      setSavedContent(content)
      void messageApi.success(t('agents.skills.saveSuccess', { defaultValue: '已保存' }))
    } catch (e) {
      showAppError(messageApi, t, e)
    } finally {
      setSaving(false)
    }
  }, [workspaceId, canManageTenantSkills, content, messageApi, t])

  const goBack = useCallback(() => {
    if (isDirty) {
      const ok = window.confirm(
        t('agents.skills.unsaved', { defaultValue: '有未保存的修改，确定离开？' }),
      )
      if (!ok) return
    }
    navigate('/app/agents/skills')
  }, [isDirty, navigate, t])

  return (
    <div className="minerva-agent-skills-page">
      <Card className="minerva-agent-skills-page__card" variant="borderless">
        <div className="minerva-agent-skills-page__toolbar">
          <Space wrap>
            <Button type="text" icon={<ArrowLeftOutlined />} onClick={goBack}>
              {t('agents.skills.backToList', { defaultValue: '返回列表' })}
            </Button>
            <Text strong>
              {t('agents.skills.registryTitle', { defaultValue: '技能注册表' })} ({INDEX_PATH})
            </Text>
          </Space>
          {canManageTenantSkills ? (
            <Button
              type="primary"
              icon={<SaveOutlined />}
              loading={saving}
              disabled={!isDirty || loading}
              onClick={() => void handleSave()}
            >
              {t('agents.skills.save', { defaultValue: '保存' })}
            </Button>
          ) : null}
        </div>
        {!canManageTenantSkills ? (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message={t('agents.skills.readOnly', {
              defaultValue: '当前账号仅可查看技能列表；上传与删除需租户所有者或管理员权限。',
            })}
          />
        ) : null}
        <div className="minerva-agent-skills-page__registry">
          <Spin spinning={loading} className="minerva-agent-skills-page__editor">
            {!loading ? (
              <SkillFileEditor
                path={INDEX_PATH}
                value={content}
                onChange={setContent}
                readOnly={!canManageTenantSkills}
              />
            ) : null}
          </Spin>
        </div>
      </Card>
    </div>
  )
}
