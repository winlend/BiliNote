/**
 * 组装导出/复制用的 Markdown 内容（与 UI 解耦）。
 */

export type ExportPreset = 'note' | 'transcript' | 'both'

export type TranscriptSegmentLike = {
  start?: number
  end?: number
  text?: string
}

export type TranscriptLike = {
  full_text?: string
  segments?: TranscriptSegmentLike[]
}

export type MarkdownVersionLike = {
  ver_id?: string
  content?: string
  created_at?: string
}

function formatTime(seconds: number): string {
  const s = Math.max(0, Math.floor(Number(seconds) || 0))
  const mins = Math.floor(s / 60)
  const secs = s % 60
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

/** 带时间轴的转写正文 */
export function formatTranscriptTimeline(transcript?: TranscriptLike | null): string {
  const segs = transcript?.segments
  if (!segs?.length) {
    const full = (transcript?.full_text || '').trim()
    return full
  }
  return segs
    .map(seg => {
      const start = formatTime(seg.start ?? 0)
      const end = formatTime(seg.end ?? seg.start ?? 0)
      const text = String(seg.text || '').trim()
      return `[${start} - ${end}] ${text}`
    })
    .filter(line => line.length > 10)
    .join('\n\n')
}

export function resolveNoteMarkdown(
  selectedContent: string | undefined | null,
  markdown: string | MarkdownVersionLike[] | undefined | null
): string {
  let content = (selectedContent || '').trim()
  if (content) return content
  if (!markdown) return ''
  if (typeof markdown === 'string') return markdown.trim()
  if (Array.isArray(markdown) && markdown.length) {
    const latest = [...markdown].sort(
      (a, b) =>
        new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()
    )[0]
    return String(latest?.content || '').trim()
  }
  return ''
}

export function buildExportMarkdown(options: {
  preset: ExportPreset
  noteMarkdown: string
  transcript?: TranscriptLike | null
  title?: string
}): { content: string; suffix: string; label: string } {
  const note = (options.noteMarkdown || '').trim()
  const transcriptBody = formatTranscriptTimeline(options.transcript)
  const title = (options.title || '').trim()

  if (options.preset === 'note') {
    return { content: note, suffix: 'note', label: '笔记' }
  }
  if (options.preset === 'transcript') {
    const header = title ? `# ${title} — 原文转写\n\n` : `# 原文转写\n\n`
    return {
      content: transcriptBody ? header + transcriptBody : '',
      suffix: 'transcript',
      label: '原文转写',
    }
  }
  // both
  const parts: string[] = []
  if (note) parts.push(note)
  if (transcriptBody) {
    parts.push('---')
    parts.push('## 原文转写（附录）')
    parts.push('')
    parts.push(transcriptBody)
  }
  return {
    content: parts.join('\n\n').trim(),
    suffix: 'note_transcript',
    label: '笔记+原文',
  }
}

export function hasTranscript(transcript?: TranscriptLike | null): boolean {
  if (!transcript) return false
  if ((transcript.segments?.length ?? 0) > 0) return true
  return Boolean((transcript.full_text || '').trim())
}
