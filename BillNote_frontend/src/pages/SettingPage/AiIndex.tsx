import { useCallback, useEffect, useMemo, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { FolderOpen, Loader2, MessageSquare, RefreshCw, Info } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { getPathConfig, openFolder, type PathConfig } from '@/services/paths'
import { getChatStatus, indexTask, type IndexStatus } from '@/services/chat'
import { useTaskStore } from '@/store/taskStore'

/**
 * 设置页：AI 问答 / 向量索引说明 + 按 task_id 重新索引
 */
export default function AiIndex() {
  const [pathConfig, setPathConfig] = useState<PathConfig | null>(null)
  const [taskId, setTaskId] = useState('')
  const [status, setStatus] = useState<IndexStatus | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [opening, setOpening] = useState(false)

  const tasks = useTaskStore(s => s.tasks)
  const currentTaskId = useTaskStore(s => s.currentTaskId)
  const successTasks = useMemo(
    () => tasks.filter(t => t.status === 'SUCCESS').slice(0, 20),
    [tasks],
  )

  useEffect(() => {
    getPathConfig()
      .then(setPathConfig)
      .catch(() => {})
    if (currentTaskId) setTaskId(currentTaskId)
  }, [currentTaskId])

  const refreshStatus = useCallback(async (id: string) => {
    if (!id.trim()) return
    try {
      const res = await getChatStatus(id.trim())
      setStatus(res.status)
      setError(res.error || '')
    } catch (e: any) {
      setStatus('failed')
      setError(e?.msg || e?.message || '查询失败')
    }
  }, [])

  useEffect(() => {
    if (taskId.trim()) refreshStatus(taskId)
  }, [taskId, refreshStatus])

  const handleReindex = async () => {
    const id = taskId.trim()
    if (!id) {
      toast.error('请填写或选择 task_id')
      return
    }
    setBusy(true)
    setStatus('indexing')
    setError('')
    try {
      await indexTask(id, { force: true })
      toast.success('已提交重新索引')
      // 简单轮询几次
      for (let i = 0; i < 30; i++) {
        await new Promise(r => setTimeout(r, 2000))
        const res = await getChatStatus(id)
        setStatus(res.status)
        setError(res.error || '')
        if (res.status === 'indexed') {
          toast.success('索引完成')
          break
        }
        if (res.status === 'failed') {
          toast.error(res.error || '索引失败')
          break
        }
      }
    } catch (e: any) {
      toast.error(e?.msg || '重新索引请求失败')
      setStatus('failed')
      setError(e?.msg || e?.message || '')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6 p-6">
      <div>
        <h2 className="text-2xl font-semibold">AI 问答 / 索引</h2>
        <p className="mt-1 text-sm text-neutral-500">
          向量索引用于笔记侧栏「AI 问答」。首次可能需联网下载 Embedding 模型。
        </p>
      </div>

      <Alert>
        <Info className="h-4 w-4" />
        <AlertDescription className="text-sm space-y-1">
          <p>
            <strong>首次索引：</strong>
            可能下载约 80MB 模型，请保持联网；进度在笔记页侧栏显示「正在建立向量索引…」。
          </p>
          <p>
            <strong>失败常见原因：</strong>
            chromadb 未打进安装包、向量库目录无写权限、笔记 json 不在当前笔记目录、网络中断。
          </p>
          <p>
            详情见后端 <code className="text-xs">logs/app.log</code>。
          </p>
        </AlertDescription>
      </Alert>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <FolderOpen className="h-5 w-5" />
            向量库路径
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p className="text-neutral-600">
            当前生效：{' '}
            <code className="rounded bg-neutral-100 px-1 text-xs break-all">
              {pathConfig?.effective?.vector_db_dir || '（加载中）'}
            </code>
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={opening}
              onClick={async () => {
                setOpening(true)
                try {
                  await openFolder('vector_db_dir')
                } catch (e: any) {
                  toast.error(e?.msg || '打开失败')
                } finally {
                  setOpening(false)
                }
              }}
            >
              打开向量库目录
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                window.location.hash = '#/settings/storage'
                // web browser router
                if (!('__TAURI_INTERNALS__' in window)) {
                  window.location.pathname = '/settings/storage'
                }
              }}
            >
              去「数据与存储」修改路径
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <MessageSquare className="h-5 w-5" />
            按任务重新索引
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-2">
            <label className="text-sm font-medium">任务 ID</label>
            <Input
              value={taskId}
              onChange={e => setTaskId(e.target.value)}
              placeholder="UUID task_id"
            />
            {successTasks.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {successTasks.map(t => (
                  <Button
                    key={t.id}
                    type="button"
                    size="sm"
                    variant={taskId === t.id ? 'default' : 'outline'}
                    className="h-7 max-w-full truncate text-xs"
                    onClick={() => setTaskId(t.id)}
                    title={t.id}
                  >
                    {(t.audioMeta?.title || t.id).slice(0, 24)}
                  </Button>
                ))}
              </div>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-neutral-500">状态：</span>
            <code className="rounded bg-neutral-100 px-1 text-xs">{status || '—'}</code>
            {error && (
              <span className="break-all text-xs text-red-500">{error}</span>
            )}
          </div>
          <div className="flex gap-2">
            <Button type="button" onClick={handleReindex} disabled={busy}>
              {busy ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="mr-2 h-4 w-4" />
              )}
              强制重新索引
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={!taskId.trim() || busy}
              onClick={() => refreshStatus(taskId)}
            >
              刷新状态
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
