/**
 * Shared TypeScript definitions for WebSocket events
 * These types ensure type-safe real-time communication
 */

export type WebSocketEventType =
  | 'job_started'
  | 'job_progress'
  | 'job_completed'
  | 'job_failed'
  | 'company_updated'
  | 'company_locked'
  | 'company_unlocked'
  | 'notification'
  | 'user_activity'
  | 'campaign_updated'
  | 'email_draft_updated';

export interface WebSocketMessage<T = any> {
  event: WebSocketEventType;
  data: T;
  user_id?: string;
  timestamp: string;
}

// Event-specific data types
export interface JobStartedData {
  job_id: string;
  job_type: string;
}

export interface JobProgressData {
  job_id: string;
  progress: number;
  status_message?: string;
}

export interface JobCompletedData {
  job_id: string;
  job_type: string;
  result?: any;
  domain_count?: number;
}

export interface JobFailedData {
  job_id: string;
  job_type: string;
  error: string;
}

export interface CompanyUpdatedData {
  company_id: string;
  status?: string;
  enriched_at?: string;
  fields_updated?: string[];
}

export interface CompanyLockedData {
  company_id: string;
  locked_by_user_id: string;
  locked_by_user_name?: string;
}

export interface CompanyUnlockedData {
  company_id: string;
}

export interface NotificationData {
  id: string;
  type: 'info' | 'success' | 'warning' | 'error';
  title: string;
  message: string;
  action_url?: string;
}

export interface UserActivityData {
  user_id: string;
  user_name: string;
  action: string;
  resource_type: string;
  resource_id: string;
  description: string;
}

export interface CampaignUpdatedData {
  campaign_id: string;
  status?: string;
  generated_count?: number;
  sent_count?: number;
}

export interface EmailDraftUpdatedData {
  draft_id: string;
  company_id: string;
  status?: string;
  gmail_draft_id?: string;
}

// Type guards for type-safe event handling
export function isJobProgressData(data: any): data is JobProgressData {
  return 'job_id' in data && 'progress' in data;
}

export function isCompanyUpdatedData(data: any): data is CompanyUpdatedData {
  return 'company_id' in data;
}

export function isNotificationData(data: any): data is NotificationData {
  return 'type' in data && 'title' in data && 'message' in data;
}
