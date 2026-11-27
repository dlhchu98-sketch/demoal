export type CitationStatus = 'PASS' | 'FAIL' | 'UNVERIFIED';
export type AppMode = 'demo' | 'live';
export type UserRole = 'user' | 'admin';

export interface UserProfile {
  id: string;
  username: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  last_login_at?: string | null;
}

export interface LegalIssueItem {
  issue: string;
  legal_domain?: string | null;
  sub_query?: string | null;
}

export interface CitationChecks {
  document_exists?: boolean | null;
  number_valid?: boolean | null;
  structure_exists?: boolean | null;
  quote_matches?: boolean | null;
  supports_claim?: boolean | null;
  validity_verified?: boolean | null;
}

export interface CitationItem {
  claim?: string | null;
  chunk_id?: string | null;
  document_id?: string | null;
  document_name: string;
  document_title?: string | null;
  document_number?: string | null;
  chapter?: string | null;
  article?: string | null;
  clause?: string | null;
  point?: string | null;
  evidence: string;
  quoted_text?: string | null;
  source?: string | null;
  source_url?: string | null;
  effective_date?: string | null;
  validity_status?: string | null;
  relevance_score?: number | null;
  validation_status: CitationStatus;
  support_status?: 'SUPPORTED' | 'UNSUPPORTED' | 'CONTRADICTED' | 'INSUFFICIENT_EVIDENCE';
  validation_reason?: string | null;
  checks?: CitationChecks | null;
}

export interface ProcessingStepItem {
  step_number: number;
  stage: string;
  label: string;
  status: 'completed' | 'warning' | 'error' | 'pending';
  detail: string;
  duration_ms?: number | null;
}

export interface ProcessingStatusInfo {
  current_step: number;
  total_steps: number;
  overall_state: 'completed' | 'completed_with_warnings' | 'insufficient_evidence' | 'error';
  steps: ProcessingStepItem[];
}

export interface SelfCorrectionStep {
  attempt: number;
  initial_status: CitationStatus;
  action: string;
  resulting_status: CitationStatus;
  detail: string;
}

export interface SelfCorrectionInfo {
  attempts: number;
  performed: boolean;
  max_attempts: number;
  steps: SelfCorrectionStep[];
}

export interface ChatResponse {
  request_id: string;
  conversation_id?: string | null;
  question: string;
  answer: string;
  conclusion: string;
  explanation: string;
  limitations: string[];
  analysis: LegalIssueItem[];
  citations: CitationItem[];
  citation_status: CitationStatus;
  verification_label: string;
  self_correction: SelfCorrectionInfo;
  processing_status: ProcessingStatusInfo;
  disclaimer: string;
  is_mock: boolean;
  app_mode: AppMode;
  processing_time_ms: number;
  created_at?: string | null;
}

export interface LegalChunkItem {
  chunk_id: string;
  document_id?: string | null;
  document_number?: string | null;
  document_title?: string | null;
  part?: string | null;
  chapter?: string | null;
  section?: string | null;
  article?: string | null;
  clause?: string | null;
  point?: string | null;
  content: string;
  source?: string | null;
  page_number?: number | null;
  effective_date?: string | null;
  chunk_index: number;
  needs_review: boolean;
}

export interface LegalDocumentSummary {
  document_id: string;
  title: string;
  document_number?: string | null;
  document_type?: string | null;
  issuing_authority?: string | null;
  issue_date?: string | null;
  effective_date?: string | null;
  expiry_date?: string | null;
  status?: string | null;
  source?: string | null;
  file_path: string;
  checksum: string;
  ingestion_date: string;
  updated_at?: string | null;
  chunk_count: number;
  qdrant_sync_status: string;
  qdrant_synced_chunks: number;
  embedding_model?: string | null;
  qdrant_collection?: string | null;
  needs_review: boolean;
  review_note?: string | null;
  last_error?: string | null;
}

export interface LegalDocumentListResponse {
  loaded: boolean;
  total_documents: number;
  total_chunks: number;
  synced_documents: number;
  failed_documents: number;
  pending_files_in_dir: number;
  document_types: string[];
  issuing_authorities: string[];
  statuses?: string[];
  items: LegalDocumentSummary[];
  note: string;
}

export interface LegalDocumentChunksResponse {
  document_id: string;
  document_title: string;
  document_number?: string | null;
  total_chunks: number;
  needs_review: boolean;
  items: LegalChunkItem[];
}
