import { useTaskStore } from '@/store/taskStore'
import { ScrollArea } from '@/components/ui/scroll-area.tsx'
import { Badge } from '@/components/ui/badge.tsx'
import { cn } from '@/lib/utils.ts'
import { RefreshCw, Trash } from 'lucide-react'
import { Button } from '@/components/ui/button.tsx'
import PinyinMatch from 'pinyin-match'
import Fuse from 'fuse.js'

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip.tsx'
import LazyImage from '@/components/LazyImage.tsx'
import { FC, useCallback, useState, useEffect, useMemo } from 'react'
import { get_task_history, type ServerTaskItem } from '@/services/note.ts'

interface NoteHistoryProps {
  onSelect: (taskId: string) => void
  selectedId: string | null
}

/** 后端返回的 created_at 是 UTC 但没带时区后缀，补 Z 再按本地时间显示 */
function formatTime(value?: string | null): string {
  if (!value) return ''
  const iso = /[zZ]|[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value}Z`
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString()
}

const NoteHistory: FC<NoteHistoryProps> = ({ onSelect, selectedId }) => {
  const tasks = useTaskStore(state => state.tasks)
  const removeTask = useTaskStore(state => state.removeTask)
  const ensureServerTask = useTaskStore(state => state.ensureServerTask)
  // 确保baseURL没有尾部斜杠
  const baseURL = (String(import.meta.env.VITE_API_BASE_URL || 'api')).replace(/\/$/, '')
  const [rawSearch, setRawSearch] = useState('')
  const [search, setSearch] = useState('')

  // 服务端历史：本地 IndexedDB 之外的历史（换设备/浏览器、脚本发起的任务）
  const [serverItems, setServerItems] = useState<ServerTaskItem[]>([])
  const [serverTotal, setServerTotal] = useState(0)
  const [serverLoading, setServerLoading] = useState(false)

  const loadServerHistory = useCallback(async () => {
    setServerLoading(true)
    try {
      const res: any = await get_task_history({ limit: 50 })
      setServerItems(res?.items ?? [])
      setServerTotal(res?.total ?? 0)
    } catch (e) {
      console.error('拉取服务端历史失败', e)
    } finally {
      setServerLoading(false)
    }
  }, [])

  useEffect(() => {
    loadServerHistory()
  }, [loadServerHistory])

  const fuse = useMemo(
    () =>
      new Fuse(tasks, {
        keys: ['audioMeta.title'],
        threshold: 0.4, // 匹配精度（越低越严格）
      }),
    [tasks]
  )
  useEffect(() => {
    const timer = setTimeout(() => {
      if (rawSearch === '') return
      setSearch(rawSearch)
    }, 300) // 300ms 防抖

    return () => clearTimeout(timer)
  }, [rawSearch])

  const filteredTasks = search.trim() ? fuse.search(search).map(result => result.item) : tasks

  // 只在服务端历史里出现的任务（本地已有的已在上面显示，避免重复）
  const localIds = useMemo(() => new Set(tasks.map(t => t.id)), [tasks])
  const serverOnly = useMemo(
    () =>
      serverItems.filter(
        it =>
          !localIds.has(it.task_id) &&
          (!search.trim() || (it.title || '').toLowerCase().includes(search.trim().toLowerCase()))
      ),
    [serverItems, localIds, search]
  )

  const handleServerClick = async (item: ServerTaskItem) => {
    await ensureServerTask(item)
    onSelect(item.task_id)
  }

  return (
    <>
      <div className="mb-2">
        <input
          type="text"
          placeholder="搜索笔记标题..."
          className="w-full rounded border border-neutral-300 px-3 py-1 text-sm outline-none focus:border-primary"
          value={rawSearch}
          onChange={e => setRawSearch(e.target.value)}
        />
      </div>

      {filteredTasks.length === 0 ? (
        <div className="rounded-md border border-neutral-200 bg-neutral-50 py-6 text-center">
          <p className="text-sm text-neutral-500">暂无记录</p>
        </div>
      ) : (
        <div className="flex flex-col gap-2 overflow-hidden">
          {filteredTasks.map(task => (
            <div
              key={task.id}
              onClick={() => onSelect(task.id)}
              className={cn(
                'flex cursor-pointer flex-col rounded-md border border-neutral-200 p-3',
                selectedId === task.id && 'border-primary bg-primary-light'
              )}
            >
              <div className={cn('flex items-center gap-4')}>
                {/* 封面图 */}
                {task.platform === 'local' ? (
                  <img
                    src={
                      task.audioMeta.cover_url ? `${task.audioMeta.cover_url}` : '/placeholder.png'
                    }
                    alt="封面"
                    className="h-10 w-12 rounded-md object-cover"
                  />
                ) : (
                  <LazyImage
                    src={
                      task.audioMeta.cover_url
                        ? `${baseURL}/image_proxy?url=${encodeURIComponent(task.audioMeta.cover_url)}`
                        : '/placeholder.png'
                    }
                    alt="封面"
                  />
                )}

                {/* 标题 + 状态 */}
                <div className="flex w-full items-center justify-between gap-2">
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <div className="line-clamp-2 max-w-[180px] flex-1 overflow-hidden text-sm text-ellipsis">
                          {task.audioMeta.title || '未命名笔记'}
                        </div>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p>{task.audioMeta.title || '未命名笔记'}</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </div>
              </div>
              <div className={'mt-2 flex items-center justify-between gap-2 text-[10px]'}>
                <div className="min-w-0 flex-1">
                  {task.status === 'SUCCESS' && (
                    <div className={'bg-primary w-10 rounded p-0.5 text-center text-white'}>
                      已完成
                    </div>
                  )}
                  {task.status !== 'SUCCESS' && task.status !== 'FAILED' ? (
                    <div className={'w-10 rounded bg-green-500 p-0.5 text-center text-white'}>
                      等待中
                    </div>
                  ) : null}
                  {task.status === 'FAILED' && (
                    <div className="flex min-w-0 flex-col gap-0.5">
                      <div className={'w-10 rounded bg-red-500 p-0.5 text-center text-white'}>
                        失败
                      </div>
                      {task.errorMessage ? (
                        <div
                          className="line-clamp-2 text-[10px] leading-snug text-red-500"
                          title={task.errorMessage}
                        >
                          {task.errorMessage}
                        </div>
                      ) : null}
                    </div>
                  )}
                </div>

                <div>
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          type="button"
                          size="small"
                          variant="ghost"
                          onClick={e => {
                            e.stopPropagation()
                            removeTask(task.id)
                          }}
                          className="shrink-0"
                        >
                          <Trash className="text-muted-foreground h-4 w-4" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p>删除</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 后端历史：本地没记录但服务端有的任务（换设备/浏览器、脚本或 API 发起的） */}
      <div className="mt-4 border-t border-neutral-200 pt-3">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-medium text-neutral-500">
            后端历史{serverTotal > 0 ? `（${serverTotal}）` : ''}
          </span>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  size="small"
                  variant="ghost"
                  onClick={loadServerHistory}
                  disabled={serverLoading}
                >
                  <RefreshCw className={cn('h-3.5 w-3.5', serverLoading && 'animate-spin')} />
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p>刷新后端历史</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>

        {serverOnly.length === 0 ? (
          <p className="text-[11px] text-neutral-400">
            {serverLoading ? '加载中…' : '没有更多历史（本地已全部包含）'}
          </p>
        ) : (
          <div className="flex flex-col gap-1.5">
            {serverOnly.map(item => (
              <div
                key={item.task_id}
                onClick={() => handleServerClick(item)}
                className={cn(
                  'cursor-pointer rounded-md border border-dashed border-neutral-200 px-3 py-2',
                  selectedId === item.task_id && 'border-primary bg-primary-light'
                )}
              >
                <div className="line-clamp-2 text-xs text-neutral-700">
                  {item.title || item.video_id}
                </div>
                <div className="mt-1 flex items-center gap-2 text-[10px] text-neutral-400">
                  <span>{formatTime(item.created_at)}</span>
                  <span>·</span>
                  <span>{item.platform}</span>
                  {item.status && item.status !== 'SUCCESS' ? (
                    <>
                      <span>·</span>
                      <span className="text-amber-600">{item.status}</span>
                    </>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  )
}

export default NoteHistory
