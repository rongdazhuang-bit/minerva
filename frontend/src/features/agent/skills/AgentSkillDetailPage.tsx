/**
 * Skill package detail: file tree, text editor, markdown preview, and binary file panel.
 */
import { ArrowLeftOutlined, SaveOutlined } from '@ant-design/icons'
import { Alert, Breadcrumb, Button, Card, Empty, Space, Spin, Tabs, Typography } from 'antd'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import { useBlocker, useNavigate, useParams } from 'react-router-dom'
import remarkGfm from 'remark-gfm'
import {
  getSkillTree,
  readSkillFile,
  writeSkillFile,
  type SkillFileTreeNode,
} from '@/api/agentSkillsMgmt'
import { useAuth } from '@/app/AuthContext'
import { useCanManageTenantSkills } from '@/components/PermGuard'
import { showAppError, useAppMessage } from '@/app/useAppMessage'
import { SkillBinaryFilePanel } from '@/features/agent/skills/components/SkillBinaryFilePanel'
import { SkillFileEditor } from '@/features/agent/skills/components/SkillFileEditor'
import { SkillFileTree } from '@/features/agent/skills/components/SkillFileTree'
import './AgentSkillsPage.css'

const { Text } = Typography

const TEXT_EXTENSIONS = new Set(['.md', '.py', '.json'])

/**
 * Returns true when the path is an editable UTF-8 text skill file.
 */
function isTextSkillFile(path: string): boolean {
  const dot = path.lastIndexOf('.')
  if (dot < 0) return false
  return TEXT_EXTENSIONS.has(path.slice(dot).toLowerCase())
}

/**
 * Finds one node in the recursive skill tree by relative path.
 */
function findTreeNode(nodes: SkillFileTreeNode[], path: string): SkillFileTreeNode | null {
  for (const node of nodes) {
    if (node.path === path) return node
    if (node.children?.length) {
      const found = findTreeNode(node.children, path)
      if (found) return found
    }
  }
  return null
}

/** Skill detail with left file tree and right editor or binary panel. */
export function AgentSkillDetailPage() {
  const { t } = useTranslation()
  const messageApi = useAppMessage()
  const navigate = useNavigate()
  const { skillId: skillIdParam } = useParams<{ skillId: string }>()
  const skillId = skillIdParam ? decodeURIComponent(skillIdParam) : ''
  const { workspaceId } = useAuth()
  const canManageTenantSkills = useCanManageTenantSkills()

  const [treeLoading, setTreeLoading] = useState(true)
  const [treeNodes, setTreeNodes] = useState<SkillFileTreeNode[]>([])
  const [selectedPath, setSelectedPath] = useState<string | undefined>()
  const [fileLoading, setFileLoading] = useState(false)
  const [content, setContent] = useState('')
  const [savedContent, setSavedContent] = useState('')
  const [saving, setSaving] = useState(false)
  const [mdTab, setMdTab] = useState<'edit' | 'preview'>('edit')
  const confirmShownRef = useRef(false)

  const isTextFile = selectedPath ? isTextSkillFile(selectedPath) : false
  const isDirty = isTextFile && content !== savedContent
  const selectedNode = useMemo(
    () => (selectedPath ? findTreeNode(treeNodes, selectedPath) : null),
    [treeNodes, selectedPath],
  )

  const loadTree = useCallback(async () => {
    if (!workspaceId || !skillId) return
    setTreeLoading(true)
    try {
      const nodes = await getSkillTree(workspaceId, skillId)
      setTreeNodes(nodes)
    } catch (e) {
      showAppError(messageApi, t, e)
    } finally {
      setTreeLoading(false)
    }
  }, [workspaceId, skillId, messageApi, t])

  useEffect(() => {
    void loadTree()
  }, [loadTree])

  const loadTextFile = useCallback(
    async (path: string) => {
      if (!workspaceId) return
      setFileLoading(true)
      try {
        const data = await readSkillFile(workspaceId, path)
        setContent(data.content)
        setSavedContent(data.content)
        setMdTab('edit')
      } catch (e) {
        showAppError(messageApi, t, e)
      } finally {
        setFileLoading(false)
      }
    },
    [workspaceId, messageApi, t],
  )

  const confirmDiscard = useCallback((): boolean => {
    if (!isDirty) return true
    return window.confirm(
      t('agents.skills.unsaved', { defaultValue: '有未保存的修改，确定离开？' }),
    )
  }, [isDirty, t])

  const handleSelectFile = useCallback(
    (path: string) => {
      if (path === selectedPath) return
      if (!confirmDiscard()) return
      setSelectedPath(path)
      if (isTextSkillFile(path)) {
        void loadTextFile(path)
      } else {
        setContent('')
        setSavedContent('')
      }
    },
    [selectedPath, confirmDiscard, loadTextFile],
  )

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
    if (!workspaceId || !canManageTenantSkills || !selectedPath) return
    if (selectedPath.toLowerCase().endsWith('.json')) {
      try {
        JSON.parse(content)
      } catch {
        void messageApi.error(
          t('agents.skills.invalidJson', { defaultValue: 'JSON 格式无效，请修正后再保存' }),
        )
        return
      }
    }
    setSaving(true)
    try {
      await writeSkillFile(workspaceId, selectedPath, content)
      setSavedContent(content)
      void messageApi.success(t('agents.skills.saveSuccess', { defaultValue: '已保存' }))
    } catch (e) {
      showAppError(messageApi, t, e)
    } finally {
      setSaving(false)
    }
  }, [workspaceId, canManageTenantSkills, selectedPath, content, messageApi, t])

  const goBack = useCallback(() => {
    if (!confirmDiscard()) return
    navigate('/app/agents/skills')
  }, [confirmDiscard, navigate])

  const handleBinaryChanged = useCallback(() => {
    setSelectedPath(undefined)
    void loadTree()
  }, [loadTree])

  const showMdPreview = selectedPath?.toLowerCase().endsWith('.md') ?? false

  const rightPanel = (() => {
    if (!selectedPath) {
      return (
        <Empty
          description={t('agents.skills.selectFile', { defaultValue: '请从左侧选择文件' })}
        />
      )
    }
    if (isTextFile) {
      const editor = (
        <div className="minerva-agent-skills-page__editor">
          <SkillFileEditor
            path={selectedPath}
            value={content}
            onChange={setContent}
            readOnly={!canManageTenantSkills}
            layoutKey={mdTab}
          />
        </div>
      )
      return (
        <Spin spinning={fileLoading} className="minerva-agent-skills-page__main-spin">
          {showMdPreview ? (
            <Tabs
              activeKey={mdTab}
              onChange={(key) => setMdTab(key as 'edit' | 'preview')}
              className="minerva-agent-skills-page__md-tabs"
              items={[
                {
                  key: 'edit',
                  label: t('agents.skills.edit', { defaultValue: '编辑' }),
                  children: editor,
                },
                {
                  key: 'preview',
                  label: t('agents.skills.preview', { defaultValue: '预览' }),
                  children: (
                    <div className="minerva-agent-skills-page__preview minerva-scrollbar-styled">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
                    </div>
                  ),
                },
              ]}
            />
          ) : (
            editor
          )}
        </Spin>
      )
    }
    if (!workspaceId) return null
    return (
      <SkillBinaryFilePanel
        workspaceId={workspaceId}
        path={selectedPath}
        size={selectedNode?.size}
        canManage={canManageTenantSkills}
        onChanged={handleBinaryChanged}
      />
    )
  })()

  return (
    <div className="minerva-agent-skills-page">
      <Card className="minerva-agent-skills-page__card minerva-page-shell-card" variant="borderless">
        <div className="minerva-agent-skills-page__toolbar">
          <Space wrap align="center">
            <Button type="text" icon={<ArrowLeftOutlined />} onClick={goBack}>
              {t('agents.skills.backToList', { defaultValue: '返回列表' })}
            </Button>
            <Breadcrumb
              items={[
                {
                  title: (
                    <a onClick={(e) => { e.preventDefault(); goBack() }}>
                      {t('agents.skills.title', { defaultValue: '技能管理' })}
                    </a>
                  ),
                },
                { title: skillId || '—' },
                ...(selectedPath ? [{ title: selectedPath }] : []),
              ]}
            />
          </Space>
          {isTextFile && canManageTenantSkills ? (
            <Button
              type="primary"
              icon={<SaveOutlined />}
              loading={saving}
              disabled={!isDirty || fileLoading}
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
        <div className="minerva-agent-skills-page__detail">
          <div className="minerva-agent-skills-page__tree minerva-scrollbar-styled">
            <Text type="secondary" className="minerva-agent-skills-page__tree-label">
              {t('agents.skills.files', { defaultValue: '文件' })}
            </Text>
            <Spin spinning={treeLoading}>
              <SkillFileTree
                nodes={treeNodes}
                selectedPath={selectedPath}
                loading={treeLoading}
                onSelectFile={handleSelectFile}
              />
            </Spin>
          </div>
          <div className="minerva-agent-skills-page__main minerva-scrollbar-styled">
            {rightPanel}
          </div>
        </div>
      </Card>
    </div>
  )
}
