/**
 * Shared TypeScript definitions for Company entities
 * These types ensure consistency between frontend and backend
 */

export interface Contact {
  type: 'email' | 'phone' | 'whatsapp' | 'address';
  value: string;
  source?: string;
  confidence?: number;
}

export interface SocialMedia {
  platform: string;
  url: string;
}

export interface Product {
  id?: string;
  name: string;
  price?: string;
  url?: string;
  image_url?: string;
  description?: string;
}

export interface Company {
  id: string;
  domain: string;
  company_name?: string;
  description?: string;
  smykm_notes?: string[];
  contacts: Contact[];
  social_media?: SocialMedia[];
  products: Product[];
  contact_score?: number;
  extracted_at?: string;
  enriched_at?: string;
  created_at: string;
  updated_at: string;
  user_id?: string;
}

export interface CompanyCreate {
  domain: string;
  company_name?: string;
  description?: string;
  smykm_notes?: string[];
}

export interface CompanyUpdate {
  company_name?: string;
  description?: string;
  smykm_notes?: string[];
}

export interface CompanyFilter {
  search?: string;
  status?: 'pending' | 'extracted' | 'enriched' | 'error';
  has_contacts?: boolean;
  has_products?: boolean;
  created_after?: string;
  created_before?: string;
}

export interface PaginatedCompanies {
  items: Company[];
  total: int;
  page: number;
  page_size: number;
  total_pages: number;
}
