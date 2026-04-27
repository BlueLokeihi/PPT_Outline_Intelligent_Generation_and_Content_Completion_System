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
}

export interface OutlinePage {
  title: string;
  bullets: string[];
  notes: string;
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
}
