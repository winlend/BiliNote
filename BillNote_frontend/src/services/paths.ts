import request from '@/utils/request'

export interface PathConfig {
  note_output_dir: string
  data_dir: string
  out_dir: string
  vector_db_dir?: string
  logs_dir?: string
  ffmpeg_bin_path: string
  config_file?: string
  suggested?: {
    data_root: string
    note_output_dir: string
    data_dir: string
    vector_db_dir: string
    logs_dir: string
    out_dir: string
  }
  effective: {
    note_output_dir: string
    data_dir: string
    out_dir: string
    vector_db_dir?: string
    ffmpeg_bin_path: string
    database_url: string
    logs_dir?: string
    cwd: string
    user_data_root?: string
    cwd_looks_like_program_files?: boolean
  }
}

export type OpenFolderWhich =
  | 'note_output_dir'
  | 'data_dir'
  | 'logs_dir'
  | 'out_dir'
  | 'vector_db_dir'
  | 'user_data_root'
  | 'cwd'

export const getPathConfig = async (): Promise<PathConfig> => {
  return await request.get('/path_config')
}

export const updatePathConfig = async (data: {
  note_output_dir?: string
  data_dir?: string
  out_dir?: string
  vector_db_dir?: string
  logs_dir?: string
  ffmpeg_bin_path?: string
  use_recommended?: boolean
}): Promise<PathConfig> => {
  return await request.post('/path_config', data)
}

/** 让后端在本机资源管理器中打开已知数据目录 */
export const openFolder = async (which: OpenFolderWhich): Promise<{ path: string }> => {
  return await request.post('/open_folder', { which })
}
