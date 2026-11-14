-- ==============================================================================
-- Initial Database Setup for AI Clinical Lab Report Explainer (PostgreSQL 16)
-- ==============================================================================

-- Enable vector search and UUID generation extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Organizations / Diagnostic Facilities
CREATE TABLE IF NOT EXISTS organizations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    license_number VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Patient Profiles (with surrogate ID for PHI protection)
CREATE TABLE IF NOT EXISTS patients (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID REFERENCES organizations(id) ON DELETE SET NULL,
    patient_identifier VARCHAR(100) UNIQUE NOT NULL,
    gender VARCHAR(20),
    birth_date DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Consolidated Lab Reports
CREATE TABLE IF NOT EXISTS lab_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID REFERENCES patients(id) ON DELETE CASCADE,
    document_sha256 VARCHAR(64) NOT NULL,
    report_date DATE,
    lab_name VARCHAR(255),
    total_tests INT DEFAULT 0,
    flagged_count INT DEFAULT 0,
    has_panic_alerts BOOLEAN DEFAULT FALSE,
    extraction_method VARCHAR(50),
    executive_summary_en TEXT,
    executive_summary_hi TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. Extracted Analyte Parameters
CREATE TABLE IF NOT EXISTS test_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_id UUID REFERENCES lab_reports(id) ON DELETE CASCADE,
    test_name VARCHAR(255) NOT NULL,
    loinc_code VARCHAR(20),
    observed_value NUMERIC,
    raw_value VARCHAR(100),
    unit VARCHAR(50),
    ref_low NUMERIC,
    ref_high NUMERIC,
    flag VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. MedlinePlus Clinical Guidelines (768-dim embeddings from gemini-embedding-2)
CREATE TABLE IF NOT EXISTS clinical_guideline_vectors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doc_id VARCHAR(100) UNIQUE NOT NULL,
    title VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    source_url TEXT,
    content TEXT NOT NULL,
    embedding vector(768),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create HNSW index for high-speed nearest-neighbor cosine retrieval
CREATE INDEX IF NOT EXISTS guideline_vector_hnsw_idx 
ON clinical_guideline_vectors 
USING hnsw (embedding vector_cosine_ops);
