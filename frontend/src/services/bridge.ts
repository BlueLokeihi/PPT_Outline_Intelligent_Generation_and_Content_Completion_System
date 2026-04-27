import type { RunOutlinePayload, RunOutlineResponse } from '@/types';

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
