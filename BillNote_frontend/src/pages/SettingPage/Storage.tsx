import { useCallback, useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { FolderOpen, HardDrive, Loader2, Save, Info, Sparkles } from 'lucide-react'
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
  const [applying, setApplying] = useState(false)
  const [opening, setOpening] = useState<string | null>(null)
  const [config, setConfig] = useState<PathConfig | null>(null)
  const [noteDir, setNoteDir] = useState('')
  const [dataDir, setDataDir] = useState('')
  const [vectorDir, setVectorDir] = useState('')
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

  const applyConfigToForm = (data: PathConfig) => {
    setConfig(data)
    setNoteDir(data.note_output_dir || data.effective?.note_output_dir || '')
    setDataDir(data.data_dir || data.effective?.data_dir || '')
    setVectorDir(data.vector_db_dir || data.effective?.vector_db_dir || '')
    setFfmpegDir(data.ffmpeg_bin_path || data.effective?.ffmpeg_bin_path || '')
  }

  const load = useCallback(async () => {
    try {
      const data = await getPathConfig()
      applyConfigToForm(data)
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
        vector_db_dir: vectorDir.trim(),
        ffmpeg_bin_path: ffmpegDir.trim(),
      })
      applyConfigToForm(data)
      toast.success('路径已保存：新任务将使用新目录（旧文件不会自动迁移）')
    } catch (e: any) {
      if (e?.msg) toast.error(e.msg)
    } finally {
      setSaving(false)
    }
  }

  const handleRecommended = async () => {
    const root = config?.suggested?.data_root || config?.effective?.user_data_root || ''
    const ok = window.confirm(
      `可选：将笔记/下载/向量库/日志切换到用户目录（安装目录写不进时再用）：\n${root}\n\n` +
        '不会自动迁移旧文件。若数据仍在安装目录，请自行复制。\n\n继续？',
    )
    if (!ok) return
    setApplying(true)
    try {
      const data = await updatePathConfig({ use_recommended: true })
      applyConfigToForm(data)
      toast.success('已应用推荐可写目录')
    } catch (e: any) {
      if (e?.msg) toast.error(e.msg)
    } finally {
      setApplying(false)
    }
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-neutral-400" />
      </div>
    )
  }

  const inProgramFiles = Boolean(config?.effective?.cwd_looks_like_program_files)

  return (
    <div className="space-y-6 p-6">
      <div>
        <h2 className="text-2xl font-semibold">数据与存储</h2>
        <p className="mt-1 text-sm text-neutral-500">
          配置笔记、下载、向量库等路径。默认优先使用安装目录（与后端工作目录相同）；若无写权限再回退到用户目录。
        </p>
      </div>

      {inProgramFiles && (
        <Alert variant="warning">
          <Info className="h-4 w-4" />
          <AlertDescription className="text-sm">
            后端工作目录在 <strong>Program Files</strong>（
            <code className="text-xs">{config?.effective?.cwd}</code>
            ）。若当前可写，默认缓存仍可放在安装目录内。若保存/索引报无权限，再点「使用推荐可写目录」或改到{' '}
            <code className="text-xs">D:\BiliNoteData\...</code>。
          </AlertDescription>
        </Alert>
      )}

      <Alert>
        <Info className="h-4 w-4" />
        <AlertDescription className="text-sm">
          修改目录后<strong>不会自动迁移</strong>旧文件。向量库用于 AI 问答索引，可与笔记目录分开配置。
          路径必须可写；不可写时保存会失败。
        </AlertDescription>
      </Alert>

      <Card>
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center justify-between gap-2 text-lg">
            <span className="flex items-center gap-2">
              <HardDrive className="h-5 w-5" />
              路径配置
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={applying}
              onClick={handleRecommended}
            >
              {applying ? (
                <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Sparkles className="mr-1 h-3.5 w-3.5" />
              )}
              使用推荐可写目录
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {config?.suggested?.data_root && (
            <p className="text-xs text-neutral-500">
              推荐数据根：{' '}
              <code className="rounded bg-neutral-100 px-1">{config.suggested.data_root}</code>
              <Button
                type="button"
                variant="link"
                className="h-auto px-1 text-xs"
                onClick={() => handleOpen('user_data_root')}
              >
                打开
              </Button>
            </p>
          )}

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
              placeholder={config?.suggested?.note_output_dir || '例如 D:/BiliNoteData/note_results'}
            />
            <p className="text-xs text-neutral-400">
              当前生效：
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
              placeholder={config?.suggested?.data_dir || '例如 D:/BiliNoteData/data'}
            />
            <p className="text-xs text-neutral-400">
              当前生效：
              <code className="ml-1 rounded bg-neutral-100 px-1">
                {config?.effective?.data_dir}
              </code>
            </p>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <label className="text-sm font-medium">向量库目录（AI 问答）</label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={opening === 'vector_db_dir'}
                onClick={() => handleOpen('vector_db_dir')}
              >
                <FolderOpen className="mr-1 h-3.5 w-3.5" />
                {opening === 'vector_db_dir' ? '打开中…' : '打开目录'}
              </Button>
            </div>
            <Input
              value={vectorDir}
              onChange={e => setVectorDir(e.target.value)}
              placeholder={
                config?.suggested?.vector_db_dir || '例如 %LOCALAPPDATA%/BiliNote/vector_db'
              }
            />
            <p className="text-xs text-neutral-400">
              Chroma 索引存放处。当前生效：
              <code className="ml-1 rounded bg-neutral-100 px-1">
                {config?.effective?.vector_db_dir}
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
              当前生效：
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
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={opening === 'logs_dir'}
              onClick={() => handleOpen('logs_dir')}
            >
              <FolderOpen className="mr-1 h-3.5 w-3.5" />
              打开日志目录
            </Button>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <span className="font-medium">后端工作目录 (CWD)：</span>
              <code className="ml-1 break-all rounded bg-neutral-100 px-1 text-xs">
                {config?.effective?.cwd}
              </code>
              {inProgramFiles && (
                <span className="ml-2 text-xs text-amber-600">（Program Files）</span>
              )}
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={opening === 'cwd'}
              onClick={() => handleOpen('cwd')}
            >
              打开
            </Button>
          </div>
          <div>
            <span className="font-medium">配置文件：</span>
            <code className="ml-1 break-all rounded bg-neutral-100 px-1 text-xs">
              {config?.config_file}
            </code>
          </div>
          <div>
            <span className="font-medium">数据库：</span>
            <code className="ml-1 break-all rounded bg-neutral-100 px-1 text-xs">
              {config?.effective?.database_url}
            </code>
            <span className="ml-2 text-xs text-neutral-400">（暂不支持在此修改）</span>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
