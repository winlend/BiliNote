/**
 * 根据失败 message / 步骤，给出可操作的设置页引导。
 */
export type ErrorGuide = {
  id: string
  label: string
  /** 相对路由，如 /settings/transcriber（HashRouter 下同样可用） */
  path: string
  hint: string
}

export function getErrorGuides(
  reason: string,
  failedStep?: string
): ErrorGuide[] {
  const text = (reason || '').toLowerCase()
  const step = (failedStep || '').toUpperCase()
  const guides: ErrorGuide[] = []
  const add = (g: ErrorGuide) => {
    if (!guides.some(x => x.id === g.id)) guides.push(g)
  }

  if (
    /groq|transcrib|whisper|model.*required|a_bogus|转写|音频/.test(text) ||
    step === 'TRANSCRIBING'
  ) {
    add({
      id: 'transcriber',
      label: '音频转写配置',
      path: '/settings/transcriber',
      hint: '检查转写引擎、Groq 转写模型；连通 Chat 不等于转写可用',
    })
  }

  if (
    /api.?key|provider|base_?url|401|403|unauthorized|供应商|openai|llm|gpt|总结/.test(
      text
    ) ||
    step === 'SUMMARIZING'
  ) {
    add({
      id: 'model',
      label: 'AI 模型设置',
      path: '/settings/model',
      hint: '检查供应商 API Key / Base URL；「测试连通性」仅验证 Chat',
    })
  }

  if (/ffmpeg|ffprobe/.test(text)) {
    add({
      id: 'storage-ffmpeg',
      label: '数据与存储 (FFmpeg)',
      path: '/settings/storage',
      hint: '配置 FFmpeg 目录或将其加入系统 PATH',
    })
  }

  if (
    /douyin|抖音|iesdouyin|_router_data|分享页|aweme/.test(text) ||
    (/download|下载/.test(text) && /douyin|抖音/.test(text))
  ) {
    add({
      id: 'download',
      label: '下载配置',
      path: '/settings/download',
      hint: '抖音现走分享页解析；仍失败可检查网络/代理或换链接',
    })
  }

  if (/cookie|bilibili|b站|412/.test(text)) {
    add({
      id: 'download-cookie',
      label: '下载配置 (Cookie)',
      path: '/settings/download',
      hint: 'B 站等平台可能需要在下载配置中填写 Cookie',
    })
  }

  if (/path|目录|permission|只读|disk|空间/.test(text)) {
    add({
      id: 'storage',
      label: '数据与存储',
      path: '/settings/storage',
      hint: '检查笔记/下载目录是否可写',
    })
  }

  // 通用兜底：日志目录入口
  add({
    id: 'logs',
    label: '打开日志目录',
    path: '/settings/storage',
    hint: '在「数据与存储」可打开 logs，查看 app.log',
  })

  return guides
}
