import { computed, ref } from 'vue';
import { defineStore } from 'pinia';
import { runOutline } from '@/services/bridge';
import type { ChatMessage, ChatSession, RunOutlineResponse } from '@/types';

function createId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function nowIso() {
  return new Date().toISOString();
}

function newSession(title = '新会话'): ChatSession {
  const ts = nowIso();
  return {
    id: createId(),
    title,
    createdAt: ts,
    updatedAt: ts,
    messages: [
      {
        id: createId(),
        role: 'system',
        text: '你可以上传PDF并发起多轮需求调整。当前会话会保留历史消息。',
        createdAt: ts,
      },
    ],
    pdfText: '',
    pdfName: '',
    status: 'idle',
    lastError: '',
  };
}

export const useChatStore = defineStore('chat', () => {
  const sessions = ref<ChatSession[]>([newSession()]);
  const activeSessionId = ref<string>(sessions.value[0].id);

  const provider = ref('qwen');
  const strategy = ref<'baseline' | 'few_shot' | 'cot_silent'>('baseline');
  const schema = ref<'on' | 'off'>('on');
  const minSlides = ref(10);
  const maxSlides = ref(18);

  const activeSession = computed(() => sessions.value.find((s) => s.id === activeSessionId.value) ?? sessions.value[0]);

  function createSession() {
    const session = newSession();
    sessions.value.unshift(session);
    activeSessionId.value = session.id;
  }

  function switchSession(sessionId: string) {
    if (!sessions.value.some((s) => s.id === sessionId)) {
      return;
    }
    activeSessionId.value = sessionId;
  }

  function touchSession(session: ChatSession) {
    session.updatedAt = nowIso();
    if (session.messages.length > 1 && session.title === '新会话') {
      const firstUser = session.messages.find((m) => m.role === 'user');
      if (firstUser) {
        session.title = firstUser.text.slice(0, 18);
      }
    }
  }

  function appendMessage(sessionId: string, message: Omit<ChatMessage, 'id' | 'createdAt'>) {
    const session = sessions.value.find((s) => s.id === sessionId);
    if (!session) {
      return;
    }
    session.messages.push({
      id: createId(),
      createdAt: nowIso(),
      ...message,
    });
    touchSession(session);
  }

  function setPdfContext(sessionId: string, fileName: string, text: string) {
    const session = sessions.value.find((s) => s.id === sessionId);
    if (!session) {
      return;
    }
    session.pdfName = fileName;
    session.pdfText = text;
    session.lastError = '';
    touchSession(session);
    appendMessage(sessionId, {
      role: 'system',
      text: `已载入 PDF: ${fileName}，可基于其内容继续对话。`,
    });
  }

  async function sendUserMessage(text: string) {
    const session = activeSession.value;
    if (!session || !text.trim()) {
      return;
    }

    appendMessage(session.id, {
      role: 'user',
      text: text.trim(),
    });

    session.status = 'running';
    session.lastError = '';

    const payload = {
      conversationId: session.id,
      messages: session.messages
        .filter((m) => m.role === 'user' || m.role === 'assistant')
        .map((m) => ({ role: m.role, text: m.text })),
      pdfText: session.pdfText,
      provider: provider.value,
      strategy: strategy.value,
      schema: schema.value,
      minSlides: minSlides.value,
      maxSlides: maxSlides.value,
    };

    const res: RunOutlineResponse = await runOutline(payload);
    if (!res.ok || !res.outline) {
      session.status = 'error';
      session.lastError = res.error ?? '生成失败';
      appendMessage(session.id, {
        role: 'assistant',
        text: `生成失败：${session.lastError}`,
        metadata: {
          provider: provider.value,
          strategy: strategy.value,
          schema: schema.value,
          elapsedS: res.elapsedS,
        },
      });
      return;
    }

    const chapterCount = res.outline.chapters.length;
    const pageCount = res.outline.chapters.reduce((acc, chapter) => acc + chapter.pages.length, 0);

    appendMessage(session.id, {
      role: 'assistant',
      text: `已生成初版大纲：《${res.outline.title}》\n章节数：${chapterCount}，页数：${pageCount}。你可以继续提出修改意见。`,
      outline: res.outline,
      metadata: {
        provider: res.provider,
        strategy: res.strategy,
        schema: res.schema,
        elapsedS: res.elapsedS,
      },
    });
    session.status = 'idle';
  }

  return {
    sessions,
    activeSessionId,
    activeSession,
    provider,
    strategy,
    schema,
    minSlides,
    maxSlides,
    createSession,
    switchSession,
    setPdfContext,
    sendUserMessage,
  };
});
