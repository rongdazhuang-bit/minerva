/**
 * Plaintext fenced code block that renders ``$...$`` / ``$$...$$`` with KaTeX while keeping copy UI.
 */
import { CopyOutlined } from '@ant-design/icons'
import { memo, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useAppMessage } from '@/app/useAppMessage'
import { copyTextToClipboard } from '@/components/markdown/copyToClipboard'
import {
  renderPlainTextMathToHtml,
  splitLineIntoPlainTextMathSegments,
  type PlainTextMathSegment,
} from '@/components/markdown/plainTextMathBlock'
import { formatCodeBlockLanguageLabel } from '@/components/markdown/prismLanguages'

type PlainTextMathCodeBlockProps = {
  code: string
  rawLanguage: string
}

/** Render one math or text segment inside a plaintext code line. */
function PlainTextMathSegmentView({ segment }: { segment: PlainTextMathSegment }) {
  if (segment.type === 'text') {
    return <>{segment.value}</>
  }

  const html = useMemo(
    () => renderPlainTextMathToHtml(segment.value, segment.type === 'display'),
    [segment.type, segment.value],
  )

  return (
    <span
      className={
        segment.type === 'display'
          ? 'minerva-md-plain-math-katex minerva-md-plain-math-katex--display'
          : 'minerva-md-plain-math-katex'
      }
      // KaTeX HTML is generated locally from model markdown (same trust model as rehype-katex).
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}

/** One line inside the plaintext math code body. */
function PlainTextMathLine({ line }: { line: string }) {
  const segments = useMemo(() => splitLineIntoPlainTextMathSegments(line), [line])

  return (
    <div className="minerva-md-plain-math-line">
      {segments.map((segment, index) => (
        <PlainTextMathSegmentView key={`${index}-${segment.type}`} segment={segment} />
      ))}
    </div>
  )
}

/** Plaintext fence with syntax header and KaTeX-aware body (agent chat). */
export const PlainTextMathCodeBlock = memo(function PlainTextMathCodeBlock({
  code,
  rawLanguage,
}: PlainTextMathCodeBlockProps) {
  const { t } = useTranslation()
  const message = useAppMessage()
  const lines = useMemo(() => code.split('\n'), [code])

  const onCopy = useCallback(async () => {
    const ok = await copyTextToClipboard(code)
    if (ok) void message.success(t('agents.copySuccess'))
    else void message.error(t('agents.copyFailed'))
  }, [code, t, message])

  const copyLabel = t('agents.copyCodeBlock')
  const languageLabel = formatCodeBlockLanguageLabel(
    rawLanguage,
    'plaintext',
    t('agents.codeLangPlainText'),
  )

  return (
    <div className="minerva-md-syntax-host minerva-md-plain-math-host">
      <div className="minerva-md-syntax-header">
        <span className="minerva-md-syntax-lang" title={languageLabel}>
          {languageLabel}
        </span>
        <button
          type="button"
          className="minerva-md-syntax-copy"
          aria-label={copyLabel}
          title={copyLabel}
          onClick={() => void onCopy()}
        >
          <CopyOutlined />
        </button>
      </div>
      <div className="minerva-md-plain-math-body">
        {lines.map((line, index) => (
          <PlainTextMathLine key={index} line={line} />
        ))}
      </div>
    </div>
  )
})
