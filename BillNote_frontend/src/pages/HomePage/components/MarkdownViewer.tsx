import { useState, useEffect, useRef, useMemo, memo, FC } from 'react'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { Button } from '@/components/ui/button.tsx'
import { Copy, Download, ArrowRight, Play, ExternalLink } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { getErrorGuides } from '@/lib/errorGuides'
import Error from '@/components/Lottie/error.tsx'
import Loading from '@/components/Lottie/Loading.tsx'
import Idle from '@/components/Lottie/Idle.tsx'
import StepBar from '@/pages/HomePage/components/StepBar.tsx'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { atomDark as codeStyle } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Zoom from 'react-medium-image-zoom'
import 'react-medium-image-zoom/dist/styles.css'
import gfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import rehypeSlug from 'rehype-slug'
import 'katex/dist/katex.min.css'
import 'github-markdown-css/github-markdown-light.css'
import { ScrollArea } from '@/components/ui/scroll-area.tsx'
import { useTaskStore } from '@/store/taskStore'
import { noteStyles } from '@/constant/note.ts'
import { MarkdownHeader } from '@/pages/HomePage/components/MarkdownHeader.tsx'
import TranscriptViewer from '@/pages/HomePage/components/transcriptViewer.tsx'
import MarkmapEditor from '@/pages/HomePage/components/MarkmapComponent.tsx'
import ChatPanel from '@/pages/HomePage/components/ChatPanel.tsx'
import VideoBanner from '@/pages/HomePage/components/VideoBanner.tsx'

interface VersionNote {
  ver_id: string
  content: string
  style: string
  model_name: string
  created_at?: string
}

interface MarkdownViewerProps {
  content: string | VersionNote[]
  status: 'idle' | 'loading' | 'success' | 'failed'
}

const steps = [
  { label: '排队', key: 'PENDING' },
  { label: '解析链接', key: 'PARSING' },
  { label: '下载音频', key: 'DOWNLOADING' },
  { label: '转写文字', key: 'TRANSCRIBING' },
  { label: '总结内容', key: 'SUMMARIZING' },
  { label: '保存', key: 'SAVING' },
  { label: '完成', key: 'SUCCESS' },
]

const STEP_HINTS: Record<string, string> = {
  PENDING: '任务已提交，等待执行…',
  PARSING: '正在解析链接并尝试获取平台字幕…',
  DOWNLOADING: '正在下载音视频，大文件或弱网会较慢…',
  TRANSCRIBING: '正在把音频转成文字。在线引擎（如 Groq）需上传音频，本地 Whisper 需推理，都可能耗时较长。',
  SUMMARIZING: 'AI 正在根据转写内容生成结构化笔记，长视频会更久…',
  FORMATTING: '正在插入截图/链接等后处理…',
  SAVING: '正在保存笔记与任务记录…',
  SUCCESS: '已完成',
  FAILED: '生成失败',
  FAILD: '生成失败',
}

const STEP_LABEL: Record<string, string> = Object.fromEntries(
  steps.map(s => [s.key, s.label]).concat([
    ['FORMATTING', '后处理'],
    ['FAILED', '失败'],
    ['RUNNING', '进行中'],
  ])
)

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}m ${s.toString().padStart(2, '0')}s`
}

function cacheResumeHint(cache?: {
  audio?: boolean
  transcript?: boolean
  markdown?: boolean
  gpt_checkpoint?: boolean
}) {
  if (!cache) {
    return {
      summary: '将尽量复用服务端已有缓存（若有）',
      detail:
        '「继续」会跳过已成功落盘的步骤；「清空后重跑」会删除转写/笔记草稿与 AI 断点后再生成。',
      hasAny: false,
    }
  }
  const kept: string[] = []
  if (cache.audio) kept.push('下载元信息')
  if (cache.transcript) kept.push('转写/字幕')
  if (cache.markdown) kept.push('笔记草稿')
  if (cache.gpt_checkpoint) kept.push('AI 分块断点')
  if (!kept.length) {
    return {
      summary: '未发现可复用缓存，两种重试都会从头执行',
      detail: '下载、转写、总结都将重新跑一遍。',
      hasAny: false,
    }
  }
  return {
    summary: `可复用：${kept.join('、')}`,
    detail:
      '点「继续」将跳过上述步骤，只重做失败及之后的环节。' +
      (cache.markdown
        ? ' 注意：若已有笔记草稿，继续可能直接复用旧草稿（换模型请用「清空后重跑」）。'
        : '') +
      ' 点「清空后重跑」会删除这些缓存与 GPT 断点后再生成（不删已下载的音视频文件）。',
    hasAny: true,
  }
}

const remarkPlugins = [gfm, remarkMath]
const rehypePlugins = [rehypeKatex, rehypeSlug]

/**
 * 构建 ReactMarkdown components 对象，baseURL 用于修正图片路径。
 * 使用函数 + useMemo 避免每次渲染都创建新的函数实例。
 */
function createMarkdownComponents(baseURL: string) {
  return {
    h1: ({ children, ...props }: any) => (
      <h1
        className="text-primary my-6 scroll-m-20 text-3xl font-extrabold tracking-tight lg:text-4xl"
        {...props}
      >
        {children}
      </h1>
    ),
    h2: ({ children, ...props }: any) => (
      <h2
        className="text-primary mt-10 mb-4 scroll-m-20 border-b pb-2 text-2xl font-semibold tracking-tight first:mt-0"
        {...props}
      >
        {children}
      </h2>
    ),
    h3: ({ children, ...props }: any) => (
      <h3
        className="text-primary mt-8 mb-4 scroll-m-20 text-xl font-semibold tracking-tight"
        {...props}
      >
        {children}
      </h3>
    ),
    h4: ({ children, ...props }: any) => (
      <h4
        className="text-primary mt-6 mb-2 scroll-m-20 text-lg font-semibold tracking-tight"
        {...props}
      >
        {children}
      </h4>
    ),
    p: ({ children, ...props }: any) => (
      <p className="leading-7 [&:not(:first-child)]:mt-6" {...props}>
        {children}
      </p>
    ),
    a: ({ href, children, ...props }: any) => {
      const isOriginLink =
        typeof children[0] === 'string' &&
        (children[0] as string).startsWith('原片 @')

      if (isOriginLink) {
        const timeMatch = (children[0] as string).match(/原片 @ (\d{2}:\d{2})/)
        const timeText = timeMatch ? timeMatch[1] : '原片'

        return (
          <span className="origin-link my-2 inline-flex">
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-full bg-blue-50 px-3 py-1 text-sm font-medium text-blue-700 transition-colors hover:bg-blue-100"
              {...props}
            >
              <Play className="h-3.5 w-3.5" />
              <span>原片（{timeText}）</span>
            </a>
          </span>
        )
      }

      // 处理笔记内部锚点链接（如目录跳转）
      if (href?.startsWith('#')) {
        const handleAnchorClick = (e: React.MouseEvent) => {
          e.preventDefault()
          const id = decodeURIComponent(href.slice(1))

          // 1. 优先精确匹配 id
          let target = document.getElementById(id)

          // 2. 精确失败时按 heading 文本模糊匹配
          // LLM 生成的目录锚点可能和 heading 实际文本不完全一致
          //（例如 heading 带 *Content-[00:00]* 后缀，目录链接里没有）
          if (!target) {
            const normalize = (s: string) =>
              s.replace(/[-：:\s*\[\]]/g, '').toLowerCase()
            const search = normalize(id)
            const headings = document.querySelectorAll('h1, h2, h3, h4, h5, h6')
            for (const h of headings) {
              const text = h.textContent || ''
              if (normalize(text).includes(search) || search.includes(normalize(text))) {
                target = h
                break
              }
            }
          }

          if (target) {
            target.scrollIntoView({ behavior: 'smooth', block: 'start' })
          } else {
            toast.error('未找到对应章节')
          }
        }

        return (
          <a
            href={href}
            onClick={handleAnchorClick}
            className="text-primary hover:text-primary/80 inline-flex items-center gap-0.5 font-medium underline underline-offset-4"
            {...props}
          >
            {children}
          </a>
        )
      }

      return (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary hover:text-primary/80 inline-flex items-center gap-0.5 font-medium underline underline-offset-4"
          {...props}
        >
          {children}
          {href?.startsWith('http') && (
            <ExternalLink className="ml-0.5 inline-block h-3 w-3" />
          )}
        </a>
      )
    },
    img: ({ node, ...props }: any) => {
      let src = props.src
      if (src.startsWith('/')) {
        src = baseURL + src
      }
      props.src = src

      return (
        <div className="my-8 flex justify-center">
          <Zoom>
            <img
              {...props}
              className="max-w-full cursor-zoom-in rounded-lg object-cover shadow-md transition-all hover:shadow-lg"
              style={{ maxHeight: '500px' }}
            />
          </Zoom>
        </div>
      )
    },
    strong: ({ children, ...props }: any) => (
      <strong className="text-primary font-bold" {...props}>
        {children}
      </strong>
    ),
    li: ({ children, ...props }: any) => {
      const rawText = String(children)
      const isFakeHeading = /^(\*\*.+\*\*)$/.test(rawText.trim())

      if (isFakeHeading) {
        return (
          <div className="text-primary my-4 text-lg font-bold">{children}</div>
        )
      }

      return (
        <li className="my-1" {...props}>
          {children}
        </li>
      )
    },
    ul: ({ children, ...props }: any) => (
      <ul className="my-6 ml-6 list-disc [&>li]:mt-2" {...props}>
        {children}
      </ul>
    ),
    ol: ({ children, ...props }: any) => (
      <ol className="my-6 ml-6 list-decimal [&>li]:mt-2" {...props}>
        {children}
      </ol>
    ),
    blockquote: ({ children, ...props }: any) => (
      <blockquote
        className="border-primary/20 text-muted-foreground mt-6 border-l-4 pl-4 italic"
        {...props}
      >
        {children}
      </blockquote>
    ),
    code: ({ inline, className, children, ...props }: any) => {
      const match = /language-(\w+)/.exec(className || '')
      const codeContent = String(children).replace(/\n$/, '')

      if (!inline && match) {
        return (
          <div className="group bg-muted relative my-6 overflow-hidden rounded-lg border shadow-sm">
            <div className="bg-muted text-muted-foreground flex items-center justify-between px-4 py-1.5 text-sm font-medium">
              <div>{match[1].toUpperCase()}</div>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(codeContent)
                  toast.success('代码已复制')
                }}
                className="bg-background/80 hover:bg-background flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-colors"
              >
                <Copy className="h-3.5 w-3.5" />
                复制
              </button>
            </div>
            <SyntaxHighlighter
              style={codeStyle}
              language={match[1]}
              PreTag="div"
              className="!bg-muted !m-0 !p-0"
              customStyle={{
                margin: 0,
                padding: '1rem',
                background: 'transparent',
                fontSize: '0.9rem',
              }}
              {...props}
            >
              {codeContent}
            </SyntaxHighlighter>
          </div>
        )
      }

      return (
        <code
          className="bg-muted relative rounded px-[0.3rem] py-[0.2rem] font-mono text-sm"
          {...props}
        >
          {children}
        </code>
      )
    },
    table: ({ children, ...props }: any) => (
      <div className="my-6 w-full overflow-y-auto">
        <table className="w-full border-collapse text-sm" {...props}>
          {children}
        </table>
      </div>
    ),
    th: ({ children, ...props }: any) => (
      <th
        className="border-muted-foreground/20 border px-4 py-2 text-left font-medium [&[align=center]]:text-center [&[align=right]]:text-right"
        {...props}
      >
        {children}
      </th>
    ),
    td: ({ children, ...props }: any) => (
      <td
        className="border-muted-foreground/20 border px-4 py-2 text-left [&[align=center]]:text-center [&[align=right]]:text-right"
        {...props}
      >
        {children}
      </td>
    ),
    hr: ({ ...props }: any) => (
      <hr className="border-muted-foreground/20 my-8" {...props} />
    ),
  }
}

const MarkdownViewer: FC<MarkdownViewerProps> = memo(({ status }) => {
  const [copied, setCopied] = useState(false)
  const [currentVerId, setCurrentVerId] = useState<string>('')
  const [selectedContent, setSelectedContent] = useState<string>('')
  const [modelName, setModelName] = useState<string>('')
  const [style, setStyle] = useState<string>('')
  const [createTime, setCreateTime] = useState<string>('')
  // 确保baseURL没有尾部斜杠
  const baseURL = (String(import.meta.env.VITE_API_BASE_URL || '').replace('/api','') || '').replace(/\/$/, '')
  const getCurrentTask = useTaskStore.getState().getCurrentTask
  const navigate = useNavigate()
  const currentTask = useTaskStore(state => state.getCurrentTask())
  const taskStatus = currentTask?.status || 'PENDING'
  const retryTask = useTaskStore.getState().retryTask
  const isMultiVersion = Array.isArray(currentTask?.markdown)
  const [showTranscribe, setShowTranscribe] = useState(false)
  const [showChat, setShowChat] = useState<false | 'half' | 'full'>(false)
  const [viewMode, setViewMode] = useState<'map' | 'preview'>('preview')
  const svgRef = useRef<SVGSVGElement>(null)
  const [elapsedSec, setElapsedSec] = useState(0)
  const [retrying, setRetrying] = useState<'continue' | 'clear' | null>(null)
  const stepStartedAt = useRef<number>(Date.now())
  const lastStepRef = useRef<string>(taskStatus)

  // 步骤切换时重置计时；同一步每秒刷新
  useEffect(() => {
    if (status !== 'loading') return
    if (lastStepRef.current !== taskStatus) {
      lastStepRef.current = taskStatus
      stepStartedAt.current = Date.now()
      setElapsedSec(0)
    }
    const t = setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - stepStartedAt.current) / 1000))
    }, 1000)
    return () => clearInterval(t)
  }, [status, taskStatus, currentTask?.id])

  // 缓存 ReactMarkdown components，仅在 baseURL 变化时重建
  const markdownComponents = useMemo(() => createMarkdownComponents(baseURL), [baseURL])

  // 多版本内容处理
  useEffect(() => {
    if (!currentTask) return

    if (!isMultiVersion) {
      setCurrentVerId('') // 清空旧版本 ID
      setModelName(currentTask.formData.model_name)
      setStyle(currentTask.formData.style)
      setCreateTime(currentTask.createdAt)
      setSelectedContent(currentTask?.markdown)
    } else {
      const latestVersion = [...currentTask.markdown].sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      )[0]

      if (latestVersion) {
        setCurrentVerId(latestVersion.ver_id)
      }
    }
  }, [currentTask?.id, taskStatus])
  useEffect(() => {
    if (!currentTask || !isMultiVersion) return

    const currentVer = currentTask.markdown.find(v => v.ver_id === currentVerId)
    if (currentVer) {
      setModelName(currentVer.model_name)
      setStyle(currentVer.style)
      setCreateTime(currentVer.created_at || '')
      setSelectedContent(currentVer.content)
    }
  }, [currentVerId, currentTask?.id])
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(selectedContent)
      setCopied(true)
      toast.success('已复制到剪贴板')
      setTimeout(() => setCopied(false), 2000)
    } catch (e) {
      toast.error('复制失败')
    }
  }
  const alertButton = {
    id: 'alert',
    title: '测试警告',
    content: '⚠️',
    onClick: () => alert('你点击了自定义按钮！'),
  }
  const exportButton = {
    id: 'export',
    title: '导出思维导图',
    content: '⤓',
    onClick: () => {
      const svgEl = svgRef.current
      if (!svgEl) return
      // 同上面的序列化逻辑
      const serializer = new XMLSerializer()
      const source = serializer.serializeToString(svgEl)
      const blob = new Blob(['<?xml version="1.0" encoding="UTF-8"?>', source], {
        type: 'image/svg+xml;charset=utf-8',
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'mindmap.svg'
      a.click()
      URL.revokeObjectURL(url)
    },
  }
  const handleDownload = () => {
    try {
      // 优先用当前选中内容；多版本/空 state 时回退到任务里的 markdown
      let content = (selectedContent || '').trim()
      if (!content && currentTask) {
        const md = currentTask.markdown
        if (typeof md === 'string') content = md.trim()
        else if (Array.isArray(md) && md.length) {
          const latest = [...md].sort(
            (a, b) =>
              new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()
          )[0]
          content = (latest?.content || '').trim()
        }
      }
      if (!content) {
        toast.error('当前没有可导出的 Markdown 内容')
        return
      }

      const rawTitle =
        currentTask?.audioMeta?.title ||
        getCurrentTask()?.audioMeta?.title ||
        'note'
      const safeName = String(rawTitle)
        .replace(/[\\/:*?"<>|]+/g, '_')
        .replace(/\s+/g, ' ')
        .trim()
        .slice(0, 80) || 'note'

      const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${safeName}.md`
      link.rel = 'noopener'
      document.body.appendChild(link)
      link.click()
      // 延迟 revoke，避免部分 WebView 还没开始下载就失效
      setTimeout(() => {
        try {
          document.body.removeChild(link)
        } catch {
          /* ignore */
        }
        URL.revokeObjectURL(url)
      }, 1000)
      toast.success('已开始下载 Markdown')
    } catch (e) {
      console.error('导出 Markdown 失败', e)
      toast.error('导出失败，请尝试「复制」后自行保存')
    }
  }

  if (status === 'loading') {
    const stepKey = taskStatus === 'RUNNING' ? 'PARSING' : taskStatus
    const detail =
      currentTask?.statusMessage ||
      STEP_HINTS[stepKey] ||
      '正在处理，请稍候…'
    const label = STEP_LABEL[stepKey] || stepKey
    return (
      <div className="flex h-screen w-full flex-col items-center justify-center space-y-4 px-6 text-neutral-500">
        <div className="w-full max-w-2xl">
          <StepBar steps={steps} currentStep={stepKey} />
        </div>
        <Loading className="h-5 w-5" />
        <div className="max-w-lg text-center text-sm">
          <p className="text-lg font-bold text-neutral-800">
            {label}
            <span className="text-primary ml-2 text-base font-medium">
              · {formatElapsed(elapsedSec)}
            </span>
          </p>
          <p className="mt-2 text-sm text-neutral-600">{detail}</p>
          <p className="mt-3 text-xs text-neutral-400">
            长视频的下载 / 转写 / 总结都可能超过一分钟，计时在走说明任务仍在进行。
          </p>
        </div>
      </div>
    )
  }

  if (status === 'idle') {
    return (
      <div className="flex h-screen w-full flex-col items-center justify-center space-y-3 text-neutral-500">
        <Idle />
        <div className="text-center">
          <p className="text-lg font-bold">输入视频链接并点击"生成笔记"</p>
          <p className="mt-2 text-xs text-neutral-500">支持哔哩哔哩、YouTube 、抖音等视频平台</p>
        </div>
      </div>
    )
  }

  if (status === 'failed' && !isMultiVersion) {
    const failedAt =
      currentTask?.failedAtStatus ||
      currentTask?.statusMessage ||
      'UNKNOWN'
    // 步骤条用失败步定位；若未知则落到 TRANSCRIBING 附近不强制
    const failedStepKey = steps.some(s => s.key === failedAt)
      ? failedAt
      : failedAt === 'FORMATTING'
        ? 'SUMMARIZING'
        : 'TRANSCRIBING'
    const reason =
      currentTask?.errorMessage ||
      currentTask?.statusMessage ||
      '请检查后台日志或稍后再试'
    const resume = cacheResumeHint(currentTask?.cache)
    const failedLabel = STEP_LABEL[failedStepKey] || failedStepKey
    const guides = getErrorGuides(reason, failedStepKey)

    const handleRetry = async (clearCache: boolean) => {
      if (!currentTask) return
      if (clearCache) {
        const ok = window.confirm(
          '确定清空该任务的下载元信息/转写/笔记草稿/AI 断点并从头重跑？\n' +
            '不会删除 DATA 目录里的音视频文件，也不会删除历史成功笔记 JSON。',
        )
        if (!ok) return
      }
      setRetrying(clearCache ? 'clear' : 'continue')
      try {
        await retryTask(currentTask.id, undefined, { clearCache })
      } finally {
        setRetrying(null)
      }
    }

    return (
      <div className="flex h-screen w-full flex-col items-center justify-center gap-4 px-6">
        <div className="w-full max-w-2xl">
          <StepBar
            steps={steps}
            currentStep={failedStepKey}
            failedStep={failedStepKey}
          />
        </div>
        <Error />
        <div className="max-w-lg text-center">
          <p className="text-lg font-bold text-red-500">笔记生成失败</p>
          <p className="mt-1 text-sm text-neutral-600">
            失败步骤：<span className="font-medium text-red-500">{failedLabel}</span>
          </p>
          <div className="mt-3 rounded-md border border-red-100 bg-red-50 px-4 py-3 text-left text-sm text-red-700 break-words">
            {reason}
          </div>
          <div className="mt-3 rounded-md border border-amber-100 bg-amber-50 px-3 py-2 text-left text-xs text-amber-900">
            <p className="font-medium">{resume.summary}</p>
            <p className="mt-1 text-amber-800/90">{resume.detail}</p>
          </div>
          {guides.length > 0 && (
            <div className="mt-4 rounded-md border border-neutral-200 bg-neutral-50 px-3 py-3 text-left">
              <p className="mb-2 text-xs font-medium text-neutral-700">建议处理</p>
              <ul className="space-y-2">
                {guides.map(g => (
                  <li key={g.id} className="flex items-start justify-between gap-2 text-xs">
                    <span className="text-neutral-600">
                      <span className="font-medium text-neutral-800">{g.label}</span>
                      {' — '}
                      {g.hint}
                    </span>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="shrink-0"
                      onClick={() => navigate(g.path)}
                    >
                      前往
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="mt-4 flex flex-wrap items-center justify-center gap-3">
            <Button
              onClick={() => handleRetry(false)}
              size="lg"
              disabled={!!retrying}
            >
              {retrying === 'continue' ? '提交中…' : '继续（复用缓存）'}
            </Button>
            <Button
              variant="destructive"
              size="lg"
              disabled={!!retrying}
              onClick={() => handleRetry(true)}
            >
              {retrying === 'clear' ? '清空中…' : '清空后重跑'}
            </Button>
            <Button
              variant="outline"
              size="lg"
              disabled={!!retrying}
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(reason)
                  toast.success('已复制错误信息')
                } catch {
                  toast.error('复制失败')
                }
              }}
            >
              复制错误
            </Button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-screen w-full flex-col overflow-hidden">
      <MarkdownHeader
        currentTask={currentTask}
        isMultiVersion={isMultiVersion}
        currentVerId={currentVerId}
        setCurrentVerId={setCurrentVerId}
        modelName={modelName}
        style={style}
        noteStyles={noteStyles}
        onCopy={handleCopy}
        onDownload={handleDownload}
        createAt={createTime}
        showTranscribe={showTranscribe}
        setShowTranscribe={setShowTranscribe}
        showChat={showChat}
        setShowChat={setShowChat}
        viewMode={viewMode}
        setViewMode={setViewMode}
      />

      {viewMode === 'map' ? (
        <div className="flex w-full flex-1 overflow-hidden bg-white">
          <div className={'w-full'}>
            <MarkmapEditor
              value={selectedContent}
              onChange={() => {}}
              height="100%" // 根据需求可以设定百分比或固定高度
              title={currentTask?.audioMeta?.title || '思维导图'}
            />
          </div>
        </div>
      ) : (
        <div className="flex flex-1 overflow-hidden bg-white py-2">
          {selectedContent && selectedContent !== 'loading' && selectedContent !== 'empty' ? (
            <>
              {showChat === 'full' && currentTask ? (
                <div className="h-full w-full">
                  <ChatPanel taskId={currentTask.id} mode="full" onModeChange={setShowChat} />
                </div>
              ) : (
              <>
              <ScrollArea className="min-w-0 flex-1">
                <div className="px-2">
                  <VideoBanner
                    audioMeta={currentTask?.audioMeta}
                    videoUrl={currentTask?.formData?.video_url}
                  />
                </div>
                <div className={'markdown-body w-full px-2'}>
                  <ReactMarkdown
                    remarkPlugins={remarkPlugins}
                    rehypePlugins={rehypePlugins}
                    components={markdownComponents}
                  >
                    {selectedContent.replace(/^>\s*来源链接：[^\n]*\n*/m, '')}
                  </ReactMarkdown>
                </div>
              </ScrollArea>
              {showTranscribe && (
                <div className={'ml-2 w-2/4'}>
                  <TranscriptViewer />
                </div>
              )}
              {/* 侧边问答模式：markdown + ChatPanel 各占一半 */}
              {showChat === 'half' && currentTask && (
                <div className="ml-2 h-full w-1/2 shrink-0">
                  <ChatPanel taskId={currentTask.id} mode="half" onModeChange={setShowChat} />
                </div>
              )}
              </>
              )}
            </>
          ) : (
            <div className="flex h-full w-full items-center justify-center">
              <div className="w-[300px] flex-col justify-items-center">
                <div className="bg-primary-light mb-4 flex h-16 w-16 items-center justify-center rounded-full">
                  <ArrowRight className="text-primary h-8 w-8" />
                </div>
                <p className="mb-2 text-neutral-600">输入视频链接并点击"生成笔记"按钮</p>
                <p className="text-xs text-neutral-500">支持哔哩哔哩、YouTube等视频网站</p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
})

MarkdownViewer.displayName = 'MarkdownViewer'

export default MarkdownViewer
