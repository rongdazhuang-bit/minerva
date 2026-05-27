/**
 * Ant Design tree for one skill package directory from getSkillTree.
 */
import { Tree, type TreeDataNode } from 'antd'
import type { Key } from 'react'
import { useMemo } from 'react'
import type { SkillFileTreeNode } from '@/api/agentSkillsMgmt'

type SkillFileTreeProps = {
  /** Recursive tree nodes from the skills-mgmt API. */
  nodes: SkillFileTreeNode[]
  /** Currently selected file path, if any. */
  selectedPath?: string
  /** Whether the tree data is still loading. */
  loading?: boolean
  /** Invoked when the user selects a file leaf (not a directory). */
  onSelectFile: (path: string) => void
}

/**
 * Maps API tree nodes to Ant Design TreeDataNode entries keyed by relative path.
 */
function toTreeData(nodes: SkillFileTreeNode[]): TreeDataNode[] {
  return nodes.map((node) => ({
    key: node.path,
    title: node.name,
    isLeaf: !node.is_dir,
    children: node.children?.length ? toTreeData(node.children) : undefined,
  }))
}

/**
 * Renders a scrollable file tree for one skill; directory clicks expand only, files invoke onSelectFile.
 */
export function SkillFileTree({
  nodes,
  selectedPath,
  loading,
  onSelectFile,
}: SkillFileTreeProps) {
  const treeData = useMemo(() => toTreeData(nodes), [nodes])

  const handleSelect = (keys: Key[]) => {
    const key = keys[0]
    if (typeof key !== 'string') return
    const node = findNode(nodes, key)
    if (!node || node.is_dir) return
    onSelectFile(key)
  }

  return (
    <Tree
      className="minerva-agent-skills-page__tree-inner"
      showLine
      blockNode
      treeData={treeData}
      selectedKeys={selectedPath ? [selectedPath] : []}
      onSelect={handleSelect}
      disabled={loading}
    />
  )
}

/**
 * Finds one node in the recursive tree by relative path.
 */
function findNode(nodes: SkillFileTreeNode[], path: string): SkillFileTreeNode | null {
  for (const node of nodes) {
    if (node.path === path) return node
    if (node.children?.length) {
      const found = findNode(node.children, path)
      if (found) return found
    }
  }
  return null
}
