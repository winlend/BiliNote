import request from '@/utils/request'

export interface PathConfig {
  note_output_dir: string
  data_dir: string
  out_dir: string
  ffmpeg_bin_path: string
  effective: {
    note_output_dir: string
    data_dir: string
    out_dir: string
    ffmpeg_bin_path: string
    database_url: string
    cwd: string
  }
}

export const getPathConfig = async (): Promise<PathConfig> => {
  return await request.get('/path_config')
}

export const updatePathConfig = async (data: {
  note_output_dir?: string
  data_dir?: string
  out_dir?: string
  ffmpeg_bin_path?: string
}): Promise<PathConfig> => {
  return await request.post('/path_config', data)
}
