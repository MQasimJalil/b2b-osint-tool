-- Add relevance_status and relevance_reason fields to companies table
-- This allows filtering out companies with no relevant products after extraction

ALTER TABLE companies
ADD COLUMN IF NOT EXISTS relevance_status VARCHAR DEFAULT 'pending',
ADD COLUMN IF NOT EXISTS relevance_reason TEXT;

-- Create index for faster filtering
CREATE INDEX IF NOT EXISTS idx_companies_relevance_status ON companies(relevance_status);

-- Update existing companies to 'relevant' if they have been extracted
UPDATE companies
SET relevance_status = 'relevant'
WHERE extracted_at IS NOT NULL AND relevance_status = 'pending';

COMMIT;
