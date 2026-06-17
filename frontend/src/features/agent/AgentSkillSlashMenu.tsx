/**
 * Slash-command menu for picking an agent skill in the composer.
 */
import { useEffect, useMemo, useRef } from 'react'
import { filterSlashSkillOptions } from '@/features/agent/agentSkillUi'

export type AgentSkillSlashOption = {
  id: string
  description: string
}

type Props = {
  open: boolean
  options: AgentSkillSlashOption[]
  filter: string
  activeIndex: number
  onPick: (skillId: string) => void
  onHoverIndex: (index: number) => void
}

/** Scroll the active option into view inside the menu list only (never the page). */
function scrollActiveSlashItemIntoView(list: HTMLUListElement, index: number) {
  const item = list.children[index] as HTMLElement | undefined
  if (!item) return
  const itemTop = item.offsetTop
  const itemBottom = itemTop + item.offsetHeight
  const viewTop = list.scrollTop
  const viewBottom = viewTop + list.clientHeight
  if (itemTop < viewTop) {
    list.scrollTop = itemTop
  } else if (itemBottom > viewBottom) {
    list.scrollTop = itemBottom - list.clientHeight
  }
}

/** Filtered skill list shown above the composer when user types ``/``. */
export function AgentSkillSlashMenu({
  open,
  options,
  filter,
  activeIndex,
  onPick,
  onHoverIndex,
}: Props) {
  const listRef = useRef<HTMLUListElement | null>(null)

  const filtered = useMemo(() => filterSlashSkillOptions(options, filter), [options, filter])

  useEffect(() => {
    if (!open || !listRef.current) return
    scrollActiveSlashItemIntoView(listRef.current, activeIndex)
  }, [activeIndex, open, filtered.length])

  if (!open || filtered.length === 0) return null

  return (
    <ul
      ref={listRef}
      className="agents-page__skill-slash-menu minerva-scrollbar-thin"
      role="listbox"
    >
      {filtered.map((opt, idx) => (
        <li
          key={opt.id}
          role="option"
          aria-selected={idx === activeIndex}
          className={
            idx === activeIndex
              ? 'agents-page__skill-slash-item agents-page__skill-slash-item--active'
              : 'agents-page__skill-slash-item'
          }
          onMouseDown={(e) => e.preventDefault()}
          onMouseEnter={() => onHoverIndex(idx)}
          onClick={() => onPick(opt.id)}
        >
          <span className="agents-page__skill-slash-id">/{opt.id}</span>
          <span className="agents-page__skill-slash-desc">{opt.description}</span>
        </li>
      ))}
    </ul>
  )
}
