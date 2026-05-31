export type MessageRole = 'system' | 'user' | 'assistant';

export interface ChatMessage {
  id: string;
  role: MessageRole;
  text: string;
  createdAt: string;
  outline?: OutlineResult;
  metadata?: {
    provider?: string;
    strategy?: string;
    schema?: 'on' | 'off';
    elapsedS?: number;
    rag?: RagResultMeta;
    quality?: QualityMetrics;
    version?: OutlineVersionMeta;
  };
}

export interface ChatSession {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: ChatMessage[];
  pdfText: string;
  pdfName: string;
  editableOutline?: OutlineResult;
  status: 'idle' | 'running' | 'error';
  lastError: string;
}

export interface RunOutlinePayload {
  conversationId: string;
  messages: Array<{ role: MessageRole; text: string }>;
  pdfText: string;
  provider: string;
  strategy: 'baseline' | 'few_shot' | 'cot_silent';
  schema: 'on' | 'off';
  minSlides: number;
  maxSlides: number;
  useRag?: boolean;
  corpusId?: string;
  ragMode?: RagMode;
}

export interface OutlineConflict {
  type: string;
  severity?: 'low' | 'medium' | 'high';
  message: string;
  sources?: string[];
  signals?: string[];
}

export interface OutlineEvidence {
  text: string;
  source: string;
  score?: number;
  chunk_index?: number;
}

export interface OutlinePage {
  title: string;
  bullets: string[];
  notes: string;
  evidences?: OutlineEvidence[];
  conflicts?: OutlineConflict[];
}

export type RagMode = 'vector' | 'bm25' | 'hybrid';

export interface RagPageMeta {
  chapter_idx: number;
  page_idx: number;
  page_title: string;
  enrichment: string;
  coverage?: number;
  confidence?: 'high' | 'medium' | 'low';
  used_source_ids?: number[];
  n_evidences?: number;
  conflicts?: OutlineConflict[];
  error?: string;
}

export interface RagResultMeta {
  used: boolean;
  corpus?: string;
  mode?: RagMode;
  embedding_model?: string;
  index_size?: number;
  rewrite_threshold?: number;
  max_rounds?: number;
  page_meta?: RagPageMeta[];
  elapsed_s?: number;
  error?: string;
}

export interface RagCorpusSource {
  id: string;
  file_count: number;
  total_bytes: number;
  source_updated_at?: string;
  has_index: boolean;
  size?: number;
  dim?: number;
  embedding_model?: string;
  built_at?: string;
  has_bm25?: boolean;
}

// ── Questionnaire ──────────────────────────────────────────────────────
export interface QuestionOption {
  id: string;   // 'a' | 'b' | 'c'
  label: string;
}

export interface QuestionItem {
  id: string;
  question: string;
  options: QuestionOption[];
  allow_custom: boolean;
  allow_ai_decide: boolean;
}

export interface QuestionnaireAnswer {
  questionId: string;
  type: 'option' | 'custom' | 'ai_decide';
  optionId?: string;
  optionLabel?: string;
  customText?: string;
}

export interface QuestionnaireResponse {
  ok: boolean;
  needs_questionnaire: boolean;
  questions: QuestionItem[];
  error?: string;
}

export interface RagCorpusInfo {
  id: string;
  size: number;
  dim: number;
  embedding_model: string;
  built_at: string;
  has_bm25: boolean;
}

export interface OutlineChapter {
  title: string;
  pages: OutlinePage[];
}

export interface OutlineResult {
  title: string;
  assumptions?: string[];
  chapters: OutlineChapter[];
}

export interface QualityMetrics {
  slide_count: number;
  chapter_count: number;
  avg_bullets_per_slide: number;
  unique_slide_title_ratio: number;
  granularity_score_0_100: number;
  hierarchy_score_0_100: number;
  coherence_score_0_100: number;
  overall_score_0_100: number;
}

export interface OutlineVersionMeta {
  versionId: string;
  conversationId?: string;
  createdAt: string;
  sourceType: 'generated' | 'edited' | 'rag' | 'restored';
  provider?: string;
  strategy?: string;
  schema?: 'on' | 'off';
  useRag?: boolean;
  summary: string;
}

export interface OutlineVersionDetail extends OutlineVersionMeta {
  outline: OutlineResult;
}

export interface RunOutlineResponse {
  ok: boolean;
  error?: string;
  elapsedS?: number;
  provider?: string;
  strategy?: string;
  schema?: 'on' | 'off';
  outline?: OutlineResult;
  rag?: RagResultMeta;
  quality?: QualityMetrics;
  version?: OutlineVersionMeta;
}

export interface SaveOutlinePayload {
  conversationId?: string;
  outline: OutlineResult;
}

export interface SaveOutlineResponse {
  ok: boolean;
  file?: string;
  relativePath?: string;
  error?: string;
}

export interface CreateVersionPayload {
  conversationId?: string;
  outline: OutlineResult;
  sourceType?: 'generated' | 'edited' | 'rag' | 'restored';
  provider?: string;
  strategy?: string;
  schemaMode?: 'on' | 'off';
  useRag?: boolean;
  summary?: string;
}

export interface VersionListResponse {
  ok: boolean;
  versions: OutlineVersionMeta[];
  error?: string;
}

export interface VersionCreateResponse {
  ok: boolean;
  version?: OutlineVersionMeta;
  error?: string;
}

export interface VersionRestoreResponse {
  ok: boolean;
  outline?: OutlineResult;
  version?: OutlineVersionMeta;
  error?: string;
}

export type ExportFormat = 'markdown' | 'html' | 'pptx' | 'json';

export interface ExportOutlinePayload {
  conversationId?: string;
  outline: OutlineResult;
  format: ExportFormat;
  report?: Record<string, unknown>;
}
