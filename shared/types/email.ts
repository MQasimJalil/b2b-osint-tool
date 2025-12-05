/**
 * Shared TypeScript definitions for Email and Campaign entities
 */

export type CampaignStatus =
  | 'draft'
  | 'generating'
  | 'ready'
  | 'sending'
  | 'completed';

export type EmailDraftStatus =
  | 'pending'
  | 'generated'
  | 'saved_to_gmail'
  | 'sent'
  | 'error';

export interface Campaign {
  id: string;
  name: string;
  status: CampaignStatus;
  total_companies: number;
  generated_count: number;
  sent_count: number;
  created_at: string;
  updated_at: string;
  user_id: string;
  company_ids: string[];
}

export interface CampaignCreate {
  name: string;
  company_ids: string[];
}

export interface CampaignUpdate {
  name?: string;
  status?: CampaignStatus;
}

export interface EmailDraft {
  id: string;
  campaign_id: string;
  company_id: string;
  company_domain: string;
  subject_lines: string[];
  selected_subject?: string;
  email_body: string;
  status: EmailDraftStatus;
  gmail_draft_id?: string;
  sent_at?: string;
  created_at: string;
  user_id: string;
}

export interface EmailDraftCreate {
  campaign_id: string;
  company_id: string;
}

export interface EmailDraftUpdate {
  selected_subject?: string;
  email_body?: string;
  status?: EmailDraftStatus;
}

export interface EmailGenerationRequest {
  company_id: string;
  sender_info?: {
    name?: string;
    company?: string;
    value_prop?: string;
  };
}

export interface EmailGenerationResponse {
  subject_lines: string[];
  email_body: string;
  smykm_references: string[];
}
