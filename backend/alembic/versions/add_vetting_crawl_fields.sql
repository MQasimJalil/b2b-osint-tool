-- Migration: Add vetting and crawl status fields to companies table
-- Date: 2025-11-26
-- Description: Adds fields to track vetting, crawling, extraction, and embedding status

-- Add vetting fields
ALTER TABLE companies
ADD COLUMN IF NOT EXISTS vetting_status VARCHAR,
ADD COLUMN IF NOT EXISTS vetting_score FLOAT,
ADD COLUMN IF NOT EXISTS vetting_details TEXT,
ADD COLUMN IF NOT EXISTS vetted_at TIMESTAMP WITH TIME ZONE;

-- Add crawl fields
ALTER TABLE companies
ADD COLUMN IF NOT EXISTS crawl_status VARCHAR DEFAULT 'not_crawled',
ADD COLUMN IF NOT EXISTS crawl_progress INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS crawled_pages INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS crawled_at TIMESTAMP WITH TIME ZONE;

-- Add embedding field
ALTER TABLE companies
ADD COLUMN IF NOT EXISTS embedded_at TIMESTAMP WITH TIME ZONE;

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_companies_vetting_status ON companies(vetting_status);
CREATE INDEX IF NOT EXISTS idx_companies_crawl_status ON companies(crawl_status);

-- Comments for documentation
COMMENT ON COLUMN companies.vetting_status IS 'Vetting status: pending, approved, rejected';
COMMENT ON COLUMN companies.vetting_score IS 'Keyword relevance score (0.0-1.0)';
COMMENT ON COLUMN companies.vetting_details IS 'JSON with detailed vetting results';
COMMENT ON COLUMN companies.crawl_status IS 'Crawl status: not_crawled, queued, crawling, completed, failed';
COMMENT ON COLUMN companies.crawl_progress IS 'Crawl progress percentage (0-100)';
COMMENT ON COLUMN companies.crawled_pages IS 'Number of pages crawled';
