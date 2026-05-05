export interface VideoInfo {
  id: number
  filename: string
  duration: number
  fps: number
  width?: number
  height?: number
  status: 'uploaded' | 'detecting' | 'detected' | 'analyzing' | 'completed' | 'error'
  error_msg?: string
  created_at: string
}

export interface NarrativeLevel {
  scene: string
  event: string
  information: string
}

export interface ShotAnalysis {
  shot_scale: string
  composition: string
  camera_movement: string
  lighting: string
  color_tone: string
  content_description: string
  on_screen_text: string
  dialogue: string
  audio?: {
    dialogue?: string
    sound_type?: string
    music?: string
    ambient_sound?: string
    speaker_emotion?: string
  }
  audiovisual_sync?: string
  audio_narrative_role?: string
  what: string
  how: string
  why: string
  narrative_level: NarrativeLevel
  emotional_function: string
  narrative_decision: string
  rhythm_contribution: string
  analysis_source?: 'whole_video' | 'chunk_segment' | 'merged_context' | 'shot_clip' | string
  analysis_mode?: 'single' | 'merged_context' | 'whole_video_context' | 'chunk_segment_context' | 'shot_clip' | string
  target_shot_index?: number
  analysis_shot_indices?: number[]
  merged_start_time?: number
  merged_end_time?: number
  target_offset_start?: number
  target_offset_end?: number
  context_shot_summaries?: Array<{
    shot_index?: number
    shot_scale?: string
    summary?: string
    action?: string
    role?: string
  }>
  merged_segment_analysis?: string
  audio_continuity?: {
    continues_from_previous?: boolean
    continues_to_next?: boolean
    unfinished_dialogue?: boolean
    notes?: string
  }
  action_continuity?: {
    continues_from_previous?: boolean
    continues_to_next?: boolean
    notes?: string
  }
  chunk_index?: number
  error?: string
}

export interface SegmentAnalysis {
  segment_index?: number
  shot_indices: number[]
  segment_type?: string
  title?: string
  summary?: string
  merge_reason?: string
  audio_continuity?: string
  action_continuity?: string
  editing_logic?: string
  emotional_arc?: string
  narrative_function?: string
  analysis_source?: string
  chunk_index?: number
}

export interface VideoSegmentReport {
  strategy?: string
  reason?: string
  shot_count?: number
  segments: SegmentAnalysis[]
}

export interface Shot {
  id: number
  index: number
  start_time: number
  end_time: number
  duration: number
  thumbnail_path?: string
  clip_path?: string
  analysis?: ShotAnalysis
}

export interface ContinuityReport {
  continuity?: {
    shot_scale_flow: string
    movement_coherence: string
    emotional_arc: string
    color_continuity: string
  }
  rhythm?: {
    avg_shot_duration: number
    shortest_shot: number
    longest_shot: number
    plot_change_frequency: string
    info_density_pattern: string
    pacing_assessment: string
    tension_peaks: string[]
  }
  narrative_structure?: {
    detected_genre: string
    three_act: string
    key_turning_points: string[]
    information_release_strategy: string
  }
  genre_patterns?: {
    structural_notes: string
    deviation_notes: string
  }
  raw?: string
  error?: string
}

export interface AnalysisResult {
  video: VideoInfo
  shots: Shot[]
  overall_analysis?: ContinuityReport
  segments?: VideoSegmentReport
}

export interface TaskProgress {
  stage: 'starting' | 'cutting_clips' | 'analyzing' | 'continuity' | 'completed' | 'error' | 'cancelled' | 'not_found'
  done?: number
  total?: number
  msg?: string
}
