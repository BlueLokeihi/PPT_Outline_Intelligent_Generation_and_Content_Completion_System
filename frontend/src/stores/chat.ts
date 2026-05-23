import { computed, ref } from 'vue';
import { defineStore } from 'pinia';
import { runOutline } from '@/services/bridge';
import type { ChatMessage, ChatSession, OutlineResult, RagMode, RunOutlineResponse } from '@/types';

function createId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function nowIso() {
  return new Date().toISOString();
}

function cloneOutline(outline: OutlineResult): OutlineResult {
  if (typeof structuredClone === 'function') {
    return structuredClone(outline);
  }
  return JSON.parse(JSON.stringify(outline)) as OutlineResult;
}

function normalizeText(text: string, fallback: string) {
  const trimmed = text.trim();
  return trimmed ? trimmed : fallback;
}

function findLatestOutline(messages: ChatMessage[]): OutlineResult | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].outline) {
      return messages[i].outline ?? null;
    }
  }
  return null;
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
  const useRag = ref(false);
  const corpusId = ref('');
  const ragMode = ref<RagMode>('hybrid');

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

  function deleteSession(sessionId: string) {
    const index = sessions.value.findIndex((s) => s.id === sessionId);
    if (index === -1) return;
    sessions.value.splice(index, 1);
    if (sessions.value.length === 0) {
      const session = newSession();
      sessions.value.push(session);
    }
    if (activeSessionId.value === sessionId) {
      activeSessionId.value = sessions.value[0].id;
    }
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

  function ensureEditableOutline(session: ChatSession): OutlineResult | null {
    if (!session.editableOutline) {
      const latest = findLatestOutline(session.messages);
      if (latest) {
        session.editableOutline = cloneOutline(latest);
      }
    }
    return session.editableOutline ?? null;
  }

  function setEditableOutline(outline: OutlineResult | null) {
    const session = activeSession.value;
    if (!session) {
      return;
    }
    session.editableOutline = outline ? cloneOutline(outline) : undefined;
    touchSession(session);
  }

  function updateOutlineTitle(title: string) {
    const session = activeSession.value;
    if (!session) return;
    const outline = ensureEditableOutline(session);
    if (!outline) return;
    outline.title = normalizeText(title, '未命名大纲');
    touchSession(session);
  }

  function updateChapterTitle(chapterIndex: number, title: string) {
    const session = activeSession.value;
    if (!session) return;
    const outline = ensureEditableOutline(session);
    if (!outline || !outline.chapters[chapterIndex]) return;
    outline.chapters[chapterIndex].title = normalizeText(title, '未命名章节');
    touchSession(session);
  }

  function updatePageTitle(chapterIndex: number, pageIndex: number, title: string) {
    const session = activeSession.value;
    if (!session) return;
    const outline = ensureEditableOutline(session);
    const page = outline?.chapters[chapterIndex]?.pages?.[pageIndex];
    if (!page) return;
    page.title = normalizeText(title, '未命名页面');
    touchSession(session);
  }

  function updatePageNotes(chapterIndex: number, pageIndex: number, notes: string) {
    const session = activeSession.value;
    if (!session) return;
    const outline = ensureEditableOutline(session);
    const page = outline?.chapters[chapterIndex]?.pages?.[pageIndex];
    if (!page) return;
    page.notes = notes;
    touchSession(session);
  }

  function updateBulletText(chapterIndex: number, pageIndex: number, bulletIndex: number, text: string) {
    const session = activeSession.value;
    if (!session) return;
    const outline = ensureEditableOutline(session);
    const page = outline?.chapters[chapterIndex]?.pages?.[pageIndex];
    if (!page || bulletIndex < 0 || bulletIndex >= page.bullets.length) return;
    page.bullets[bulletIndex] = text;
    touchSession(session);
  }

  function addChapter(afterIndex?: number) {
    const session = activeSession.value;
    if (!session) return;
    const outline = ensureEditableOutline(session);
    if (!outline) return;
    const insertAt = typeof afterIndex === 'number' ? afterIndex + 1 : outline.chapters.length;
    outline.chapters.splice(insertAt, 0, {
      title: '新章节',
      pages: [
        {
          title: '新页面',
          bullets: ['新要点'],
          notes: '',
        },
      ],
    });
    touchSession(session);
  }

  function removeChapter(index: number) {
    const session = activeSession.value;
    if (!session) return;
    const outline = ensureEditableOutline(session);
    if (!outline || !outline.chapters[index]) return;
    outline.chapters.splice(index, 1);
    touchSession(session);
  }

  function moveChapter(index: number, direction: -1 | 1) {
    const session = activeSession.value;
    if (!session) return;
    const outline = ensureEditableOutline(session);
    if (!outline) return;
    const target = index + direction;
    if (target < 0 || target >= outline.chapters.length) return;
    const [item] = outline.chapters.splice(index, 1);
    outline.chapters.splice(target, 0, item);
    touchSession(session);
  }

  function addPage(chapterIndex: number, afterIndex?: number) {
    const session = activeSession.value;
    if (!session) return;
    const outline = ensureEditableOutline(session);
    const chapter = outline?.chapters[chapterIndex];
    if (!chapter) return;
    const insertAt = typeof afterIndex === 'number' ? afterIndex + 1 : chapter.pages.length;
    chapter.pages.splice(insertAt, 0, {
      title: '新页面',
      bullets: ['新要点'],
      notes: '',
    });
    touchSession(session);
  }

  function removePage(chapterIndex: number, pageIndex: number) {
    const session = activeSession.value;
    if (!session) return;
    const outline = ensureEditableOutline(session);
    const chapter = outline?.chapters[chapterIndex];
    if (!chapter || !chapter.pages[pageIndex]) return;
    chapter.pages.splice(pageIndex, 1);
    touchSession(session);
  }

  function movePage(chapterIndex: number, pageIndex: number, direction: -1 | 1) {
    const session = activeSession.value;
    if (!session) return;
    const outline = ensureEditableOutline(session);
    const chapter = outline?.chapters[chapterIndex];
    if (!chapter) return;
    const target = pageIndex + direction;
    if (target < 0 || target >= chapter.pages.length) return;
    const [item] = chapter.pages.splice(pageIndex, 1);
    chapter.pages.splice(target, 0, item);
    touchSession(session);
  }

  function addBullet(chapterIndex: number, pageIndex: number, afterIndex?: number) {
    const session = activeSession.value;
    if (!session) return;
    const outline = ensureEditableOutline(session);
    const page = outline?.chapters[chapterIndex]?.pages?.[pageIndex];
    if (!page) return;
    const insertAt = typeof afterIndex === 'number' ? afterIndex : page.bullets.length;
    page.bullets.splice(insertAt, 0, '新要点');
    touchSession(session);
  }

  function removeBullet(chapterIndex: number, pageIndex: number, bulletIndex: number) {
    const session = activeSession.value;
    if (!session) return;
    const outline = ensureEditableOutline(session);
    const page = outline?.chapters[chapterIndex]?.pages?.[pageIndex];
    if (!page || bulletIndex < 0 || bulletIndex >= page.bullets.length) return;
    page.bullets.splice(bulletIndex, 1);
    touchSession(session);
  }

  function moveBullet(chapterIndex: number, pageIndex: number, bulletIndex: number, direction: -1 | 1) {
    const session = activeSession.value;
    if (!session) return;
    const outline = ensureEditableOutline(session);
    const page = outline?.chapters[chapterIndex]?.pages?.[pageIndex];
    if (!page) return;
    const target = bulletIndex + direction;
    if (target < 0 || target >= page.bullets.length) return;
    const [item] = page.bullets.splice(bulletIndex, 1);
    page.bullets.splice(target, 0, item);
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
      useRag: useRag.value && !!corpusId.value,
      corpusId: corpusId.value,
      ragMode: ragMode.value,
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

    const ragSuffix = res.rag?.used
      ? `\nRAG: corpus=${res.rag.corpus} · ${res.rag.mode}` +
        (typeof res.rag.elapsed_s === 'number' ? ` · ${res.rag.elapsed_s.toFixed(1)}s` : '')
      : '';

    appendMessage(session.id, {
      role: 'assistant',
      text: `已生成初版大纲：《${res.outline.title}》\n章节数：${chapterCount}，页数：${pageCount}。你可以继续提出修改意见。${ragSuffix}`,
      outline: res.outline,
      metadata: {
        provider: res.provider,
        strategy: res.strategy,
        schema: res.schema,
        elapsedS: res.elapsedS,
        rag: res.rag,
        quality: res.quality,
        version: res.version,
      },
    });
    setEditableOutline(res.outline);
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
    useRag,
    corpusId,
    ragMode,
    createSession,
    switchSession,
    deleteSession,
    setPdfContext,
    sendUserMessage,
    setEditableOutline,
    updateOutlineTitle,
    updateChapterTitle,
    updatePageTitle,
    updatePageNotes,
    updateBulletText,
    addChapter,
    removeChapter,
    moveChapter,
    addPage,
    removePage,
    movePage,
    addBullet,
    removeBullet,
    moveBullet,
  };
});
