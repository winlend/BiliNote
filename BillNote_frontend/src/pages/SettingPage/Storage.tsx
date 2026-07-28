import { useCallback, useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { FolderOpen, HardDrive, Loader2, Save, Info } from 'lucide-react'
import { toast } from 'react-hot-toast'
import {
  getPathConfig,
  updatePathConfig,
  openFolder,
  PathConfig,
  OpenFolderWhich,
} from '@/services/paths'

export default function Storage() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [opening, setOpening] = useState<string | null>(null)
  const [config, setConfig] = useState<PathConfig | null>(null)
  const [noteDir, setNoteDir] = useState('')
  const [dataDir, setDataDir] = useState('')
  const [ffmpegDir, setFfmpegDir] = useState('')

  const handleOpen = async (which: OpenFolderWhich) => {
    setOpening(which)
    try {
      const res = await openFolder(which)
      toast.success(`已打开：${res?.path || which}`)
    } catch (e: any) {
      if (e?.msg) toast.error(e.msg)
      else toast.error('打开目录失败')
    } finally {
      setOpening(null)
    }
  }

  const load = useCallback(async () => {
    try {
      const data = await getPathConfig()
      setConfig(data)
      setNoteDir(data.note_output_dir || data.effective?.note_output_dir || '')
      setDataDir(data.data_dir || data.effective?.data_dir || '')
      setFfmpegDir(data.ffmpeg_bin_path || data.effective?.ffmpeg_bin_path || '')
    } catch {
      toast.error('获取路径配置失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const handleSave = async () => {
    setSaving(true)
    try {
      const data = await updatePathConfig({
        note_output_dir: noteDir.trim(),
        data_dir: dataDir.trim(),
        ffmpeg_bin_path: ffmpegDir.trim(),
      })
      setConfig(data)
      setNoteDir(data.note_output_dir || data.effective?.note_output_dir || '')
      setDataDir(data.data_dir || data.effective?.data_dir || '')
      setFfmpegDir(data.ffmpeg_bin_path || data.effective?.ffmpeg_bin_path || '')
      toast.success('路径已保存：新任务将使用新目录（旧文件不会自动迁移）')
    } catch (e: any) {
      // 拦截器可能已 toast
      if (e?.msg) toast.error(e.msg)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-neutral-400" />
      </div>
    )
  }

  return (
    <div className="space-y-6 p-6">
      <div>
        <h2 className="text-2xl font-semibold">数据与存储</h2>
        <p className="mt-1 text-sm text-neutral-500">
          配置笔记缓存、下载目录与 FFmpeg 路径。优先于环境变量；建议使用绝对路径。
        </p>
      </div>

      <Alert>
        <Info className="h-4 w-4" />
        <AlertDescription className="text-sm">
          修改目录后<strong>不会自动迁移</strong>旧文件。若需保留历史笔记/缓存，请手动复制到新目录。
          数据库路径暂不支持在此修改（改后需重启）。
        </AlertDescription>
      </Alert>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <HardDrive className="h-5 w-5" />
            路径配置
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <label className="text-sm font-medium">笔记与任务缓存目录</label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={opening === 'note_output_dir'}
                onClick={() => handleOpen('note_output_dir')}
              >
                <FolderOpen className="mr-1 h-3.5 w-3.5" />
                {opening === 'note_output_dir' ? '打开中…' : '打开目录'}
              </Button>
            </div>
            <Input
              value={noteDir}
              onChange={e => setNoteDir(e.target.value)}
              placeholder="例如 D:/BiliNoteData/note_results"
            />
            <p className="text-xs text-neutral-400">
              存放 status / 转写缓存 / 成功笔记 JSON。当前生效：
              <code className="ml-1 rounded bg-neutral-100 px-1">
                {config?.effective?.note_output_dir}
              </code>
            </p>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <label className="text-sm font-medium">下载缓存目录</label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={opening === 'data_dir'}
                onClick={() => handleOpen('data_dir')}
              >
                <FolderOpen className="mr-1 h-3.5 w-3.5" />
                {opening === 'data_dir' ? '打开中…' : '打开目录'}
              </Button>
            </div>
            <Input
              value={dataDir}
              onChange={e => setDataDir(e.target.value)}
              placeholder="例如 D:/BiliNoteData/data"
            />
            <p className="text-xs text-neutral-400">
              音视频下载缓存。当前生效：
              <code className="ml-1 rounded bg-neutral-100 px-1">
                {config?.effective?.data_dir}
              </code>
            </p>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">FFmpeg 目录（可选）</label>
            <Input
              value={ffmpegDir}
              onChange={e => setFfmpegDir(e.target.value)}
              placeholder="例如 D:/Program Files/FFmpeg/bin"
            />
            <p className="text-xs text-neutral-400">
              填 bin 目录或 ffmpeg 可执行文件路径。当前生效：
              <code className="ml-1 rounded bg-neutral-100 px-1">
                {config?.effective?.ffmpeg_bin_path || '（系统 PATH）'}
              </code>
            </p>
          </div>

          <Button onClick={handleSave} disabled={saving} className="mt-2">
            {saving ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Save className="mr-2 h-4 w-4" />
            )}
            保存配置
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <FolderOpen className="h-5 w-5" />
            只读信息
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-neutral-600">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <span className="font-medium">日志目录：</span>
              <code className="ml-1 break-all rounded bg-neutral-100 px-1 text-xs">
                {config?.effective?.logs_dir || '(logs)'}
              </code>
              <span className="ml-2 text-xs text-neutral-400">app.log 在此</span>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={opening === 'logs_dir'}
              onClick={() => handleOpen('logs_dir')}
            >
              <FolderOpen className="mr-1 h-3.5 w-3.5" />
              {opening === 'logs_dir' ? '打开中…' : '打开日志目录'}
            </Button>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <span className="font-medium">后端工作目录 (CWD)：</span>
              <code className="ml-1 break-all rounded bg-neutral-100 px-1 text-xs">
                {config?.effective?.cwd}
              </code>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={opening === 'cwd'}
              onClick={() => handleOpen('cwd')}
            >
              <FolderOpen className="mr-1 h-3.5 w-3.5" />
              打开
            </Button>
          </div>
          <div>
            <span className="font-medium">数据库：</span>
            <code className="ml-1 break-all rounded bg-neutral-100 px-1 text-xs">
              {config?.effective?.database_url}
            </code>
            <span className="ml-2 text-xs text-neutral-400">（设置页暂不支持修改）</span>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
