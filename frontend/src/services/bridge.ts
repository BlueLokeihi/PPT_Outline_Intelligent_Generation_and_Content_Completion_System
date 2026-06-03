import type {
  CreateVersionPayload,
  ExportOutlinePayload,
  QuestionnaireResponse,
  RagCorpusInfo,
  RagCorpusSource,
  RunOutlinePayload,
  RunOutlineResponse,
  SaveOutlinePayload,
  SaveOutlineResponse,
  VersionCreateResponse,
  VersionListResponse,
  VersionRestoreResponse,
  WebSearchResult,
} from '@/types';

const apiBase = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');
const serviceNotAvailableMessage =
  '未检测到本地HTTP服务。请先在 backend 目录启动 python http_server.py。';

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
    ...init,
  });

  const data = (await response.json()) as T;
  return data;
}

async function requestBlob(path: string, init?: RequestInit): Promise<{ ok: boolean; blob?: Blob; fileName?: string; error?: string }> {
  try {
    const response = await fetch(`${apiBase}${path}`, {
      headers: {
        'Content-Type': 'application/json',
        ...(init?.headers || {}),
      },
      ...init,
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      return { ok: false, error: data.error || response.statusText };
    }
    const disposition = response.headers.get('content-disposition') || '';
    const match = /filename="?([^"]+)"?/i.exec(disposition);
    return {
      ok: true,
      blob: await response.blob(),
      fileName: match?.[1],
    };
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : serviceNotAvailableMessage,
    };
  }
}

export async function requestQuestionnaire(topic: string, provider: string): Promise<QuestionnaireResponse> {
  try {
    return await requestJson<QuestionnaireResponse>('/questionnaire', {
      method: 'POST',
      body: JSON.stringify({ topic, provider }),
    });
  } catch {
    return { ok: false, needs_questionnaire: false, questions: [] };
  }
}

export async function pingBridge() {
  try {
    return await requestJson<{ ok: boolean; message: string }>('/ping', {
      method: 'POST',
      body: '{}',
    });
  } catch {
    return { ok: false, message: serviceNotAvailableMessage };
  }
}

export async function getRuntimeInfo() {
  try {
    return await requestJson<{ ok: boolean; providers: string[]; strategies: string[] }>('/runtime-info', {
      method: 'GET',
    });
  } catch {
    return {
      ok: false,
      providers: [],
      strategies: [],
    };
  }
}

export async function runOutline(payload: RunOutlinePayload): Promise<RunOutlineResponse> {
  try {
    return await requestJson<RunOutlineResponse>('/outline', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : serviceNotAvailableMessage,
    };
  }
}

export async function getCorpora(): Promise<{ ok: boolean; corpora: RagCorpusInfo[] }> {
  try {
    return await requestJson<{ ok: boolean; corpora: RagCorpusInfo[] }>('/rag/corpora', {
      method: 'GET',
    });
  } catch {
    return { ok: false, corpora: [] };
  }
}

export async function getCorpusSources(): Promise<{ ok: boolean; sources: RagCorpusSource[] }> {
  try {
    return await requestJson<{ ok: boolean; sources: RagCorpusSource[] }>('/rag/corpus-sources', {
      method: 'GET',
    });
  } catch {
    return { ok: false, sources: [] };
  }
}

export async function saveOutline(payload: SaveOutlinePayload): Promise<SaveOutlineResponse> {
  try {
    return await requestJson<SaveOutlineResponse>('/outline/save', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : serviceNotAvailableMessage,
    };
  }
}

export async function createOutlineVersion(payload: CreateVersionPayload): Promise<VersionCreateResponse> {
  try {
    return await requestJson<VersionCreateResponse>('/outline/versions', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : serviceNotAvailableMessage,
    };
  }
}

export async function listOutlineVersions(conversationId: string): Promise<VersionListResponse> {
  try {
    return await requestJson<VersionListResponse>(`/outline/versions?conversationId=${encodeURIComponent(conversationId)}`, {
      method: 'GET',
    });
  } catch (error) {
    return {
      ok: false,
      versions: [],
      error: error instanceof Error ? error.message : serviceNotAvailableMessage,
    };
  }
}

export async function restoreOutlineVersion(versionId: string): Promise<VersionRestoreResponse> {
  try {
    return await requestJson<VersionRestoreResponse>(`/outline/versions/${encodeURIComponent(versionId)}/restore`, {
      method: 'POST',
      body: '{}',
    });
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : serviceNotAvailableMessage,
    };
  }
}

export async function exportOutline(payload: ExportOutlinePayload) {
  return requestBlob('/outline/export', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function uploadCorpusFiles(
  corpusId: string,
  files: File[],
): Promise<{ ok: boolean; corpusId?: string; saved?: string[]; count?: number; indexInvalidated?: boolean; error?: string }> {
  try {
    const form = new FormData();
    form.append('corpusId', corpusId);
    for (const f of files) {
      form.append('files', f);
    }
    const response = await fetch(`${apiBase}/rag/upload`, { method: 'POST', body: form });
    return (await response.json()) as { ok: boolean; corpusId?: string; saved?: string[]; count?: number; indexInvalidated?: boolean; error?: string };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : serviceNotAvailableMessage };
  }
}

export async function buildCorpus(
  corpusId: string,
  options?: { provider?: string; model?: string; chunkSize?: number; overlap?: number },
): Promise<{ ok: boolean; corpusId?: string; exitCode?: number; error?: string }> {
  try {
    return await requestJson<{ ok: boolean; corpusId?: string; exitCode?: number; error?: string }>('/rag/corpora/build', {
      method: 'POST',
      body: JSON.stringify({
        corpusId,
        provider: options?.provider ?? 'qwen',
        model: options?.model ?? '',
        chunkSize: options?.chunkSize ?? 500,
        overlap: options?.overlap ?? 80,
      }),
    });
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : serviceNotAvailableMessage };
  }
}

export async function listCorpusFiles(
  corpusId: string,
): Promise<{ ok: boolean; files: Array<{ name: string; size: number }>; error?: string }> {
  try {
    return await requestJson<{ ok: boolean; files: Array<{ name: string; size: number }>; error?: string }>(
      `/rag/corpora/${encodeURIComponent(corpusId)}/files`,
      { method: 'GET' },
    );
  } catch {
    return { ok: false, files: [] };
  }
}

export async function deleteCorpusFile(
  corpusId: string,
  filename: string,
): Promise<{ ok: boolean; indexInvalidated?: boolean; error?: string }> {
  try {
    return await requestJson<{ ok: boolean; indexInvalidated?: boolean; error?: string }>(
      `/rag/corpora/${encodeURIComponent(corpusId)}/files/${encodeURIComponent(filename)}`,
      { method: 'DELETE' },
    );
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : serviceNotAvailableMessage };
  }
}

export async function renameCorpus(
  corpusId: string,
  newCorpusId: string,
): Promise<{ ok: boolean; corpusId?: string; newCorpusId?: string; error?: string }> {
  try {
    return await requestJson<{ ok: boolean; corpusId?: string; newCorpusId?: string; error?: string }>(
      '/rag/corpora/rename',
      { method: 'POST', body: JSON.stringify({ corpusId, newCorpusId }) },
    );
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : serviceNotAvailableMessage };
  }
}

export async function deleteCorpus(corpusId: string): Promise<{ ok: boolean; error?: string }> {
  try {
    return await requestJson<{ ok: boolean; error?: string }>(
      `/rag/corpora/${encodeURIComponent(corpusId)}`,
      { method: 'DELETE' },
    );
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : serviceNotAvailableMessage };
  }
}

// ── Web Search ─────────────────────────────────────────────────────────────
export async function searchWeb(
  query: string,
  maxResults = 8,
): Promise<{ ok: boolean; results: WebSearchResult[]; error?: string }> {
  try {
    return await requestJson<{ ok: boolean; results: WebSearchResult[]; error?: string }>(
      '/search/web',
      { method: 'POST', body: JSON.stringify({ query, maxResults }) },
    );
  } catch (error) {
    return { ok: false, results: [], error: error instanceof Error ? error.message : serviceNotAvailableMessage };
  }
}

// ── File Text Extraction ───────────────────────────────────────────────────
async function _extractFile(
  endpoint: string,
  file: File,
): Promise<{ ok: boolean; text?: string; fileName?: string; charCount?: number; error?: string }> {
  try {
    const form = new FormData();
    form.append('file', file);
    const response = await fetch(`${apiBase}${endpoint}`, { method: 'POST', body: form });
    return await response.json();
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : serviceNotAvailableMessage };
  }
}

export async function extractDocx(file: File) { return _extractFile('/extract/docx', file); }
export async function extractPptx(file: File) { return _extractFile('/extract/pptx', file); }
