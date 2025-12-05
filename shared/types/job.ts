/**
 * Shared TypeScript definitions for Job entities
 * Jobs represent background tasks (discovery, crawling, enrichment, etc.)
 */

export type JobType =
  | 'discovery'
  | 'crawling'
  | 'extraction'
  | 'enrichment'
  | 'email_generation';

export type JobStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface JobConfig {
  [key: string]: any;
}

export interface JobResult {
  [key: string]: any;
}

export interface Job {
  id: string;
  job_type: JobType;
  status: JobStatus;
  progress: number; // 0-100
  config: JobConfig;
  result?: JobResult;
  error?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  user_id: string;
  celery_task_id?: string;
}

export interface JobCreate {
  job_type: JobType;
  config: JobConfig;
}

export interface JobUpdate {
  status?: JobStatus;
  progress?: number;
  result?: JobResult;
  error?: string;
}

export interface JobProgressUpdate {
  job_id: string;
  progress: number;
  status_message?: string;
}
