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

export interface RunOutlineResponse {
  ok: boolean;
  error?: string;
  elapsedS?: number;
  provider?: string;
  strategy?: string;
  schema?: 'on' | 'off';
  outline?: OutlineResult;
  rag?: RagResultMeta;
}
