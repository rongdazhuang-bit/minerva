/**
 * Agent composer textarea with a skill chip and separate body field when a skill is selected.
 */
import { Input, type InputRef } from 'antd'
import {
  forwardRef,
  useImperativeHandle,
  useLayoutEffect,
  useMemo,
  useRef,
  type KeyboardEvent,
  type Ref,
} from 'react'
import {
  composeDraftWithSkillChip,
  parseCommittedSkillChip,
} from '@/features/agent/agentSkillUi'

type AgentComposerInputProps = {
  value: string
  onChange: (value: string) => void
  onKeyDown?: (event: KeyboardEvent<HTMLTextAreaElement>) => void
  onPressEnter?: (event: KeyboardEvent<HTMLTextAreaElement>) => void
  placeholder?: string
  disabled?: boolean
  knownSkillIds: readonly string[]
}

/** Fixed textarea height — same row count with or without a skill chip. */
const COMPOSER_AUTOSIZE = { minRows: 2, maxRows: 8 }

/** Composer with optional slash skill chip; keeps one textarea mounted to preserve focus. */
export const AgentComposerInput = forwardRef(function AgentComposerInput(
  {
    value,
    onChange,
    onKeyDown,
    onPressEnter,
    placeholder,
    disabled,
    knownSkillIds,
  }: AgentComposerInputProps,
  ref: Ref<InputRef>,
) {
  /** Forwards focus to the composer textarea. */
  const inputRef = useRef<InputRef | null>(null)
  /** Refocus after skill chip is removed via keyboard. */
  const refocusAfterChipChangeRef = useRef(false)

  useImperativeHandle(ref, () => inputRef.current as InputRef)

  const chip = useMemo(
    () => parseCommittedSkillChip(value, knownSkillIds),
    [value, knownSkillIds],
  )

  const displayValue = chip ? chip.body : value

  useLayoutEffect(() => {
    if (!refocusAfterChipChangeRef.current) return
    refocusAfterChipChangeRef.current = false
    const ref = inputRef.current as
      | (InputRef & { resizableTextArea?: { textArea: HTMLTextAreaElement }; input?: HTMLTextAreaElement })
      | null
    const el = ref?.resizableTextArea?.textArea ?? ref?.input
    el?.focus({ preventScroll: true })
  }, [chip, displayValue])

  /** Backspace at body start removes the skill chip as one unit (optionally keeping body text). */
  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (chip && event.key === 'Backspace') {
      const ta = event.currentTarget
      if (ta.selectionStart === 0) {
        event.preventDefault()
        refocusAfterChipChangeRef.current = true
        const selectedLen = ta.selectionEnd
        if (selectedLen >= chip.body.length) {
          onChange('')
          return
        }
        if (selectedLen > 0) {
          onChange(chip.body.slice(selectedLen))
          return
        }
        onChange(chip.body.length > 0 ? chip.body : '')
        return
      }
    }
    onKeyDown?.(event)
  }

  return (
    <div
      className={
        chip
          ? 'agents-page__composer-input-row agents-page__composer-input-row--skill'
          : 'agents-page__composer-input-row'
      }
    >
      {chip ? (
        <span className="agents-page__composer-skill-chip" aria-hidden>
          /{chip.skillId}
        </span>
      ) : null}
      <Input.TextArea
        ref={inputRef}
        allowClear
        variant="borderless"
        classNames={{ textarea: 'agents-page__composer-input' }}
        autoSize={COMPOSER_AUTOSIZE}
        value={displayValue}
        onChange={(e) => {
          const next = e.target.value
          onChange(chip ? composeDraftWithSkillChip(chip.skillId, next) : next)
        }}
        onKeyDown={handleKeyDown}
        onPressEnter={onPressEnter}
        placeholder={placeholder}
        disabled={disabled}
      />
    </div>
  )
})
