import { useEffect, useRef } from 'react'
import { useTaskStore } from '@/store/taskStore'
import { get_task_status } from '@/services/note.ts'
import toast from 'react-hot-toast'

function cacheResumeHint(cache?: { audio?: boolean; transcript?: boolean; markdown?: boolean }) {
  if (!cache) return ''
  const parts: string[] = []
  if (cache.audio) parts.push('下载')
  if (cache.transcript) parts.push('转写')
  if (cache.markdown) parts.push('笔记草稿')
  if (!parts.length) return '将从头执行各步骤'
  return `将复用已有缓存：${parts.join('、')}；仅重做缺失步骤`
}

export const useTaskPolling = (interval = 3000) => {
  const tasks = useTaskStore(state => state.tasks)
  const updateTaskContent = useTaskStore(state => state.updateTaskContent)

  const tasksRef = useRef(tasks)

  useEffect(() => {
    tasksRef.current = tasks
  }, [tasks])

  useEffect(() => {
    const timer = setInterval(async () => {
      const pendingTasks = tasksRef.current.filter(
        task => task.status != 'SUCCESS' && task.status != 'FAILED'
      )

      if (pendingTasks.length === 0) return

      for (const task of pendingTasks) {
        try {
          // suppressToast：任务失败是业务状态，由本处统一弹一次真实原因
          const res: any = await get_task_status(task.id)
          const status = res?.status
          const message = res?.message || ''
          const failedAt = res?.failed_at || res?.phase || undefined
          const cache = res?.cache

          if (!status || status === task.status) {
            // 同状态也更新进度文案 / 缓存信息
            if (message && message !== task.statusMessage) {
              updateTaskContent(task.id, {
                statusMessage: message,
                cache,
                failedAtStatus: failedAt,
              })
            }
            continue
          }

          if (status === 'SUCCESS') {
            const { markdown, transcript, audio_meta } = res.result || {}
            toast.success('笔记生成成功')
            updateTaskContent(task.id, {
              status,
              markdown,
              transcript,
              audioMeta: audio_meta,
              statusMessage: message || '完成',
              errorMessage: '',
              cache,
            })
          } else if (status === 'FAILED') {
            const reason = message || '笔记生成失败'
            toast.error(reason, { duration: 6000 })
            updateTaskContent(task.id, {
              status: 'FAILED',
              errorMessage: reason,
              statusMessage: reason,
              failedAtStatus: failedAt || task.status,
              cache,
            })
          } else {
            updateTaskContent(task.id, {
              status,
              statusMessage: message || undefined,
              cache,
              failedAtStatus: failedAt,
            })
          }
        } catch (e: any) {
          // 兼容旧后端仍用 code!=0 返回失败的情况
          const reason = e?.msg || e?.message || '笔记生成失败，请查看后端日志'
          console.error('❌ 任务轮询失败：', e)
          toast.error(reason, { duration: 6000 })
          updateTaskContent(task.id, {
            status: 'FAILED',
            errorMessage: reason,
            statusMessage: reason,
            failedAtStatus: task.status,
          })
        }
      }
    }, interval)

    return () => clearInterval(timer)
  }, [interval, updateTaskContent])
}

export { cacheResumeHint }
