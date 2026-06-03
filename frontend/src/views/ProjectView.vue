<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import SourcesPanel from '@/components/SourcesPanel.vue';
import ChatComposer from '@/components/ChatComposer.vue';
import RequirementsForm from '@/components/RequirementsForm.vue';
import OutlinePanel from '@/components/OutlinePanel.vue';
import DynamicQuestionnaire from '@/components/DynamicQuestionnaire.vue';
import WebSearchBlock from '@/components/WebSearchBlock.vue';
import {
  getCorpusSources, getRuntimeInfo, pingBridge, requestQuestionnaire, searchWeb,
} from '@/services/bridge';
import { useChatStore } from '@/stores/chat';
import type { OutlineResult, QuestionItem, QuestionnaireAnswer, RagCorpusInfo, RagCorpusSource, WebSearchResult } from '@/types';

const emit = defineEmits<{ goHome: [] }>();
const store = useChatStore();

// ── Resizable columns ────────────────────────────────────────────────────
const leftWidth = ref(340);
const rightWidth = ref(500);

function startResize(side: 'left' | 'right', e: MouseEvent) {
  const startX = e.clientX;
  const startW = side === 'left' ? leftWidth.value : rightWidth.value;
  const onMove = (ev: MouseEvent) => {
    const delta = ev.clientX - startX;
    if (side === 'left') {
      leftWidth.value = Math.max(160, Math.min(480, startW + delta));
    } else {
      rightWidth.value = Math.max(280, Math.min(700, startW - delta));
    }
  };
  const onUp = () => {
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  };
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
  document.body.style.cursor = 'col-resize';
  document.body.style.userSelect = 'none';
  e.preventDefault();
}

const messagesEl = ref<HTMLDivElement | null>(null);
const bridgeOk = ref(false);
const bridgeMsg = ref('检测中…');
const availableProviders = ref<string[]>(['qwen', 'deepseek', 'glm']);
const availableStrategies = ref<Array<'baseline' | 'few_shot' | 'cot_silent'>>(['baseline', 'few_shot', 'cot_silent']);
const availableCorpora = ref<RagCorpusInfo[]>([]);
const availableSources = ref<RagCorpusSource[]>([]);
const generatingSeconds = ref(0);
const viewMode = ref<'doc' | 'cards' | 'slides'>('doc');
const outlineVisible = ref(true);

// Questionnaire state
const questionnaireLoading = ref(false);
const showQuestionnaire = ref(false);
const questionnaireItems = ref<QuestionItem[]>([]);
const pendingMessage = ref('');

let generatingTimer: ReturnType<typeof setInterval> | null = null;

const activeSession = computed(() => store.activeSession);
const isGenerating = computed(() => activeSession.value?.status === 'running');
const hasUserMessages = computed(() =>
  activeSession.value?.messages.some((m) => m.role === 'user') ?? false
);
const latestOutline = computed((): OutlineResult | null => {
  const messages = activeSession.value?.messages ?? [];
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].outline) return messages[i].outline!;
  }
  return null;
});
const editableOutline = computed(() => activeSession.value?.editableOutline ?? latestOutline.value);

const suggestions = computed((): string[] => {
  if (!latestOutline.value || isGenerating.value) return [];
  const chs = latestOutline.value.chapters;
  const result: string[] = [];
  if (chs.length > 0) result.push(`细化「${chs[Math.floor(chs.length / 2)].title}」，补充数据与案例`);
  if (chs.length >= 2) result.push(`将「${chs[chs.length - 1].title}」拆为两个独立章节`);
  result.push('在开头增加执行摘要（1页）');
  const total = latestOutline.value.chapters.reduce((s, ch) => s + ch.pages.length, 0);
  result.push(`压缩总页数，控制在 ${Math.max(8, total - 2)} 页以内`);
  return result.slice(0, 4);
});

function roleLabel(role: string) {
  if (role === 'user') return '用户';
  if (role === 'assistant') return 'AI';
  return 'sys';
}
function outlinePageCount(outline: OutlineResult) {
  return outline.chapters.reduce((s, ch) => s + ch.pages.length, 0);
}

function formatQuestionnaireAnswers(answers: QuestionnaireAnswer[], questions: QuestionItem[]): string {
  const lines = ['[问卷答案]'];
  for (const ans of answers) {
    const q = questions.find((x) => x.id === ans.questionId);
    if (!q) continue;
    lines.push(`Q: ${q.question}`);
    if (ans.type === 'option') {
      const opt = q.options.find((o) => o.id === ans.optionId);
      lines.push(`A: ${ans.optionId?.toUpperCase()} — ${opt?.label ?? ans.optionLabel}`);
    } else if (ans.type === 'custom') {
      lines.push(`A: 自定义 — ${ans.customText}`);
    } else {
      lines.push('A: 由 AI 决定');
    }
  }
  return lines.join('\n');
}

// ── Web search flow ──────────────────────────────────────────────────────
async function runWebSearch(topic: string): Promise<WebSearchResult[]> {
  if (!activeSession.value) return [];
  const msgId = `ws-${Date.now()}`;
  // Show "searching" bubble
  store.upsertToolMessage(activeSession.value.id, msgId, {
    webSearch: { query: topic, results: [], status: 'searching' },
  });
  await nextTick();
  scrollToBottom();

  try {
    const res = await searchWeb(topic, 8);
    if (res.ok && res.results.length > 0) {
      store.upsertToolMessage(activeSession.value.id, msgId, {
        webSearch: { query: topic, results: res.results, status: 'done' },
      });
      // Also save to session web sources
      store.addWebSource(activeSession.value.id, {
        id: msgId,
        query: topic,
        results: res.results,
        addedAt: new Date().toISOString(),
      });
      return res.results;
    } else {
      store.upsertToolMessage(activeSession.value.id, msgId, {
        webSearch: { query: topic, results: [], status: 'error', error: res.error },
      });
      return [];
    }
  } catch {
    store.upsertToolMessage(activeSession.value.id, msgId, {
      webSearch: { query: topic, results: [], status: 'error' },
    });
    return [];
  }
}

async function sendWithWebSearch(message: string) {
  const topicMatch = message.match(/【主题】(.+)/);
  const searchTopic = topicMatch ? topicMatch[1].trim() : message.slice(0, 80);

  const webResults = await runWebSearch(searchTopic);

  // Build sources snapshot for attribution
  const session = store.activeSession;
  const sourcesMeta = {
    files: (session?.fileSources ?? []).map(f => ({ name: f.name, type: f.type })),
    webSearches: [
      ...(session?.webSources ?? []).map(ws => ({ query: ws.query, resultCount: ws.results.length })),
      ...(webResults.length > 0 ? [{ query: searchTopic, resultCount: webResults.length }] : []),
    ],
    rag: store.useRag && store.corpusId
      ? { corpus: store.corpusId, mode: store.ragMode }
      : null,
  };

  await store.sendUserMessage(message, { webResults, sourcesMeta });
}

// ── Form modal (for "生成初版大纲" button) ────────────────────────────────
const showFormModal = ref(false);

async function onFormFromModal(text: string, minSlides: number, maxSlides: number) {
  store.minSlides = minSlides;
  store.maxSlides = maxSlides;
  showFormModal.value = false;
  pendingMessage.value = text;
  await handleInitialMessage(text);
}

// ── Questionnaire flow ───────────────────────────────────────────────────
async function onSend(text: string) {
  await store.sendUserMessage(text);
}

async function onQuestionnaireSubmit(answers: QuestionnaireAnswer[]) {
  showQuestionnaire.value = false;
  const answerBlock = formatQuestionnaireAnswers(answers, questionnaireItems.value);
  const enrichedMessage = `${pendingMessage.value}\n\n${answerBlock}`;
  await sendWithWebSearch(enrichedMessage);
}

async function onQuestionnaireSkip() {
  showQuestionnaire.value = false;
  await sendWithWebSearch(pendingMessage.value);
}

// Called from HomeView when a new project is created
// (HomeView sends the first message itself after navigation)

// For follow-up messages from the composer after outline exists
watch(isGenerating, (running) => {
  if (running) {
    generatingSeconds.value = 0;
    if (generatingTimer) clearInterval(generatingTimer);
    generatingTimer = setInterval(() => { generatingSeconds.value += 1; }, 1000);
  } else {
    if (generatingTimer) { clearInterval(generatingTimer); generatingTimer = null; }
  }
});

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight;
  });
}

watch(() => activeSession.value?.messages.length, scrollToBottom);

function onCorporaUpdated(list: RagCorpusInfo[]) {
  availableCorpora.value = list;
  if (!store.corpusId && list.length > 0) store.corpusId = list[0].id;
  void refreshCorpusSources();
}

async function refreshCorpusSources() {
  const res = await getCorpusSources();
  if (res.ok) {
    availableSources.value = res.sources;
    const indexed = res.sources
      .filter((s) => s.has_index)
      .map((s) => ({
        id: s.id, size: s.size ?? 0, dim: s.dim ?? 0,
        embedding_model: s.embedding_model || 'unknown',
        built_at: s.built_at || '', has_bm25: Boolean(s.has_bm25),
      }));
    availableCorpora.value = indexed;
    if (!store.corpusId && indexed.length > 0) store.corpusId = indexed[0].id;
  }
}

onMounted(async () => {
  const [ping, runtime, sources] = await Promise.all([pingBridge(), getRuntimeInfo(), getCorpusSources()]);
  bridgeOk.value = ping.ok;
  bridgeMsg.value = ping.ok ? '已连接' : '未连接';

  if (runtime.ok) {
    if (runtime.providers.length > 0) {
      availableProviders.value = runtime.providers;
      if (!runtime.providers.includes(store.provider)) store.provider = runtime.providers[0] ?? 'qwen';
    }
    if (runtime.strategies.length > 0) {
      availableStrategies.value = runtime.strategies as Array<'baseline' | 'few_shot' | 'cot_silent'>;
      if (!runtime.strategies.includes(store.strategy)) store.strategy = (runtime.strategies[0] as any) ?? 'baseline';
    }
  }

  if (sources.ok) {
    availableSources.value = sources.sources;
    const indexed = sources.sources
      .filter((s) => s.has_index)
      .map((s) => ({
        id: s.id, size: s.size ?? 0, dim: s.dim ?? 0,
        embedding_model: s.embedding_model || 'unknown',
        built_at: s.built_at || '', has_bm25: Boolean(s.has_bm25),
      }));
    availableCorpora.value = indexed;
    if (!store.corpusId && indexed.length > 0) store.corpusId = indexed[0].id;
  }

  scrollToBottom();
});

async function handleInitialMessage(text: string) {
  questionnaireLoading.value = true;
  pendingMessage.value = text;
  try {
    const result = await requestQuestionnaire(text, store.provider);
    if (result.ok && result.needs_questionnaire && result.questions?.length > 0) {
      questionnaireItems.value = result.questions;
      questionnaireLoading.value = false;
      showQuestionnaire.value = true;
      return; // wait for questionnaire modal
    }
  } catch {
    // questionnaire failed → proceed directly
  }
  questionnaireLoading.value = false;
  await sendWithWebSearch(text);
}

onBeforeUnmount(() => {
  if (generatingTimer) { clearInterval(generatingTimer); generatingTimer = null; }
});
</script>

<template>
  <div class="pv">
    <!-- Topbar -->
    <header class="pv__topbar">
      <div class="pv__topbar-left">
        <button class="pv__back" @click="emit('goHome')" title="返回主页">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="15 18 9 12 15 6"/></svg>
          主页
        </button>
        <div class="pv__topbar-sep"></div>
        <span class="pv__project-title">{{ activeSession?.topic || activeSession?.title || 'PPT 大纲' }}</span>
        <span class="pv__topbar-status">
          <span :class="['pv__dot', bridgeOk ? '' : 'pv__dot--err']"></span>
          {{ bridgeMsg }}
        </span>
      </div>

      <div class="pv__topbar-controls">
        <div class="pv__field">
          <label>模型</label>
          <select class="pv__select" v-model="store.provider">
            <option v-for="p in availableProviders" :key="p" :value="p">{{ p }}</option>
          </select>
        </div>
        <div class="pv__sep"></div>
        <div class="pv__field">
          <label>策略</label>
          <select class="pv__select" v-model="store.strategy">
            <option v-for="s in availableStrategies" :key="s" :value="s">{{ s }}</option>
          </select>
        </div>
        <div class="pv__sep"></div>
        <div class="pv__field">
          <label>Schema</label>
          <select class="pv__select" v-model="store.schema">
            <option value="on">on</option>
            <option value="off">off</option>
          </select>
        </div>
        <div class="pv__sep" v-if="latestOutline && outlineVisible"></div>
        <template v-if="latestOutline && outlineVisible">
          <div class="pv__view-tabs">
            <button
              v-for="m in (['doc', 'cards', 'slides'] as const)"
              :key="m"
              :class="['pv__view-tab', { active: viewMode === m }]"
              @click="viewMode = m"
            >{{ m === 'doc' ? 'Doc' : m === 'cards' ? 'Cards' : 'Slides' }}</button>
          </div>
        </template>
        <div class="pv__sep"></div>
        <button class="pv__outline-toggle" @click="outlineVisible = !outlineVisible">
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
            <rect x="1" y="1" width="11" height="11" rx="2" stroke="currentColor" stroke-width="1.2"/>
            <path d="M8.5 1v11" stroke="currentColor" stroke-width="1.2"/>
          </svg>
          {{ outlineVisible ? '折叠大纲' : '展开大纲' }}
        </button>
      </div>
    </header>

    <!-- Three-column workspace -->
    <div class="pv__workspace">
      <!-- Left: Sources -->
      <div class="pv__col-sources" :style="{ width: leftWidth + 'px' }">
        <SourcesPanel
          :available-corpora="availableCorpora"
          :available-sources="availableSources"
          @corporaUpdated="onCorporaUpdated"
        />
      </div>

      <!-- Resize handle: left/middle -->
      <div class="pv__resizer" @mousedown="startResize('left', $event)" title="拖拽调整宽度"></div>

      <!-- Middle: Chat -->
      <div class="pv__col-chat">
        <div class="pv__chat">
          <div class="pv__chat-scroll" ref="messagesEl">
            <div class="pv__chat-inner">

              <!-- Empty state -->
              <div v-if="!hasUserMessages" class="pv__chat-empty">
                <template v-if="isGenerating">
                  <!-- Generating -->
                  <div class="pv__empty-generating">
                    <div class="pv__empty-spinner"></div>
                    <p class="pv__empty-gen-text">正在生成大纲，请稍候…</p>
                  </div>
                </template>
                <template v-else>
                  <!-- Ready state: prominent CTA -->
                  <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round" style="color: var(--rule-strong)"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
                  <p class="pv__empty-title">准备好了？</p>
                  <p class="pv__empty-sub">在左侧添加参考文件、搜索网络来源、选择知识库<br/>然后点击下方按钮开始生成</p>
                  <button class="pv__empty-generate-btn" @click="showFormModal = true">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                    生成初版大纲
                  </button>
                  <p class="pv__empty-hint">也可以在下方输入框左侧找到此按钮</p>
                </template>
              </div>

              <!-- Messages -->
              <template v-for="message in activeSession?.messages" :key="message.id">
                <!-- Web search block -->
                <div v-if="message.role === 'tool' && message.webSearch" class="pv__msg-tool">
                  <WebSearchBlock
                    :query="message.webSearch.query"
                    :results="message.webSearch.results"
                    :status="message.webSearch.status"
                    :error="message.webSearch.error"
                  />
                </div>

                <!-- Regular messages -->
                <div
                  v-else-if="message.role !== 'system' || message.text.startsWith('已载入')"
                  :class="['pv__msg', `pv__msg--${message.role}`]"
                >
                  <div class="pv__msg-avatar">{{ roleLabel(message.role) }}</div>
                  <div class="pv__msg-body">
                    <div class="pv__msg-head">
                      <span class="pv__msg-author">
                        {{ message.role === 'user' ? '用户' : message.role === 'assistant' ? '智能大纲' : '系统' }}
                      </span>
                      <span class="pv__msg-time">{{ new Date(message.createdAt).toLocaleTimeString() }}</span>
                    </div>
                    <div class="pv__msg-content">
                      <p class="pv__msg-text">{{ message.text }}</p>
                      <!-- Outline card -->
                      <div v-if="message.role === 'assistant' && message.outline" class="pv__moc">
                        <div class="pv__moc-head">
                          <span class="pv__moc-title">{{ message.outline.title }}</span>
                          <span class="pv__moc-stats">{{ message.outline.chapters.length }} 章 · {{ outlinePageCount(message.outline) }} 页</span>
                        </div>
                        <div class="pv__moc-rows">
                          <div v-for="(ch, i) in message.outline.chapters" :key="i" class="pv__moc-row">
                            <span class="pv__moc-num">{{ String(i + 1).padStart(2, '0') }}</span>
                            <span class="pv__moc-name">{{ ch.title }}</span>
                            <span class="pv__moc-pages">{{ ch.pages.length }}p</span>
                          </div>
                        </div>
                        <div class="pv__moc-foot">在右侧大纲面板中查看完整结构 →</div>
                      </div>
                    </div>
                    <!-- Sources attribution card -->
                    <div v-if="message.metadata?.sources" class="pv__sources-card">
                      <div class="pv__sources-title">
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                        本次生成使用的参考来源
                      </div>
                      <div class="pv__sources-list">
                        <span v-for="f in message.metadata.sources.files" :key="f.name" class="pv__source-tag pv__source-tag--file">
                          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                          {{ f.name }}
                        </span>
                        <span v-for="ws in message.metadata.sources.webSearches" :key="ws.query" class="pv__source-tag pv__source-tag--web">
                          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
                          {{ ws.query }} ({{ ws.resultCount }}条)
                        </span>
                        <span v-if="message.metadata.sources.rag" class="pv__source-tag pv__source-tag--rag">
                          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>
                          {{ message.metadata.sources.rag.corpus }} · {{ message.metadata.sources.rag.mode }}
                        </span>
                      </div>
                    </div>

                    <!-- Metadata chips -->
                    <div v-if="message.metadata" class="pv__msg-meta">
                      <span v-if="message.metadata.provider" class="pv__chip"><span class="pv__chip-k">provider</span>{{ message.metadata.provider }}</span>
                      <span v-if="message.metadata.strategy" class="pv__chip"><span class="pv__chip-k">strategy</span>{{ message.metadata.strategy }}</span>
                      <span v-if="message.metadata.elapsedS" class="pv__chip pv__chip--time">{{ message.metadata.elapsedS.toFixed(2) }}s</span>
                      <span v-if="message.metadata.quality" class="pv__chip pv__chip--quality">Q {{ message.metadata.quality.overall_score_0_100 }}</span>
                      <span v-if="message.metadata.rag?.used" class="pv__chip pv__chip--rag">RAG ✓</span>
                    </div>
                  </div>
                </div>
              </template>

              <!-- Generating bubble -->
              <div v-if="isGenerating" class="pv__msg pv__msg--assistant pv__msg--typing">
                <div class="pv__msg-avatar">AI</div>
                <div class="pv__msg-body">
                  <div class="pv__msg-head">
                    <span class="pv__msg-author">智能大纲</span>
                    <span class="pv__msg-time">{{ generatingSeconds }}s</span>
                  </div>
                  <div class="pv__typing">
                    <div class="pv__typing-step">正在生成大纲结构…</div>
                    <div class="pv__typing-bar"><div class="pv__typing-bar-fill"></div></div>
                    <div class="typing-dots"><span></span><span></span><span></span></div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <p v-if="activeSession?.lastError" class="pv__error-text">{{ activeSession.lastError }}</p>

          <div class="pv__adjust-hint" v-if="latestOutline && !isGenerating">
            继续输入修改意见以调整大纲
          </div>

          <ChatComposer
            :disabled="isGenerating"
            :suggestions="suggestions"
            :show-generate-btn="!hasUserMessages && !isGenerating"
            @send="onSend"
            @generate="showFormModal = true"
          />
        </div>
      </div>

      <!-- Resize handle: middle/right -->
      <div v-show="outlineVisible" class="pv__resizer" @mousedown="startResize('right', $event)" title="拖拽调整宽度"></div>

      <!-- Right: Outline -->
      <div v-show="outlineVisible" class="pv__col-outline" :style="{ width: rightWidth + 'px' }">
        <OutlinePanel :outline="editableOutline" :view-mode="viewMode" />
      </div>
    </div>
  </div>

  <!-- Requirements Form Modal (triggered by "生成初版大纲") -->
  <Teleport to="body">
    <div v-if="showFormModal" class="pv__modal-overlay" @click.self="showFormModal = false">
      <div class="pv__form-modal">
        <div class="pv__form-modal-head">
          <span>填写大纲需求</span>
          <button class="pv__form-modal-close" @click="showFormModal = false">×</button>
        </div>
        <RequirementsForm
          :disabled="isGenerating || questionnaireLoading"
          :loading-questionnaire="questionnaireLoading"
          @submit="onFormFromModal"
        />
      </div>
    </div>
  </Teleport>

  <!-- Questionnaire modal -->
  <Teleport to="body">
    <DynamicQuestionnaire
      v-if="showQuestionnaire"
      :questions="questionnaireItems"
      :topic="pendingMessage"
      @submit="onQuestionnaireSubmit"
      @skip="onQuestionnaireSkip"
    />
  </Teleport>
</template>

<style scoped>
.pv { display: flex; flex-direction: column; height: 100vh; overflow: hidden; background: var(--paper); }

/* Topbar */
.pv__topbar {
  display: flex; align-items: center; justify-content: space-between;
  height: 48px; padding: 0 16px; gap: 12px;
  border-bottom: 1px solid var(--rule); flex-shrink: 0;
  background: var(--paper);
}
.pv__topbar-left { display: flex; align-items: center; gap: 10px; min-width: 0; }
.pv__back {
  display: inline-flex; align-items: center; gap: 4px;
  border: none; background: transparent; font: inherit; font-size: 12px;
  color: var(--ink-3); cursor: pointer; padding: 4px 6px; border-radius: 5px;
  white-space: nowrap; transition: all .12s;
}
.pv__back:hover { background: var(--paper-3); color: var(--ink); }
.pv__topbar-sep { width: 1px; height: 16px; background: var(--rule-strong); flex-shrink: 0; }
.pv__project-title {
  font-family: var(--f-serif); font-size: 14px; font-weight: 500; color: var(--ink);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 200px;
}
.pv__topbar-status { display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--ink-3); white-space: nowrap; }
.pv__dot { width: 6px; height: 6px; border-radius: 50%; background: #22c55e; }
.pv__dot--err { background: #ef4444; }

.pv__topbar-controls {
  display: flex; align-items: center; gap: 8px; flex-shrink: 0;
}
.pv__sep { width: 1px; height: 16px; background: var(--rule-strong); }
.pv__field { display: flex; align-items: center; gap: 4px; font-size: 11px; color: var(--ink-3); white-space: nowrap; }
.pv__select {
  border: 1px solid var(--rule); border-radius: 5px; padding: 3px 6px;
  font: inherit; font-size: 11.5px; background: var(--paper); color: var(--ink);
  cursor: pointer; outline: none;
}

.pv__view-tabs { display: flex; gap: 1px; background: var(--paper-3); border-radius: var(--r-sm); padding: 2px; border: 1px solid var(--rule); }
.pv__view-tab { border: none; background: transparent; padding: 3px 11px; font-size: 11.5px; font-weight: 500; cursor: pointer; color: var(--ink-3); border-radius: 4px; transition: all .12s; font-family: inherit; white-space: nowrap; }
.pv__view-tab.active { background: var(--paper); color: var(--ink); box-shadow: 0 1px 3px var(--rule-strong); }

.pv__outline-toggle {
  display: inline-flex; align-items: center; gap: 5px;
  border: 1px solid var(--rule); border-radius: 6px; padding: 4px 10px;
  font: inherit; font-size: 11.5px; background: var(--paper); color: var(--ink-2);
  cursor: pointer; white-space: nowrap; transition: all .12s;
}
.pv__outline-toggle:hover { background: var(--paper-3); }

/* Three-column workspace — flex for easy resize */
.pv__workspace {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.pv__col-sources {
  flex-shrink: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-width: 160px;
}
.pv__col-chat {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--rule);
}
.pv__col-outline {
  flex-shrink: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-width: 280px;
}

/* Drag handle between columns */
.pv__resizer {
  width: 4px;
  flex-shrink: 0;
  background: var(--rule);
  cursor: col-resize;
  position: relative;
  z-index: 5;
  transition: background .15s;
}
.pv__resizer::before {
  content: '';
  position: absolute;
  inset: 0 -3px;
  /* Wider hit area for easier grabbing */
}
.pv__resizer:hover { background: var(--accent-stroke); }

/* Chat */
.pv__chat { flex: 1; display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
.pv__chat-scroll { flex: 1; overflow-y: auto; }
.pv__chat-inner {
  padding: 24px 24px 12px;
  display: flex;
  flex-direction: column;
  gap: 0;
  min-height: 100%;
}

.pv__chat-empty {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 40px; text-align: center; color: var(--ink-4); gap: 16px;
}

/* Generating state */
.pv__empty-generating { display: flex; flex-direction: column; align-items: center; gap: 14px; }
.pv__empty-spinner {
  width: 36px; height: 36px;
  border: 3px solid var(--rule-strong);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: empty-spin 1s linear infinite;
}
@keyframes empty-spin { to { transform: rotate(360deg); } }
.pv__empty-gen-text { font-size: 14px; color: var(--ink-3); margin: 0; }

/* Ready state */
.pv__empty-title { font-family: var(--f-serif); font-size: 20px; font-weight: 500; color: var(--ink); margin: 0; }
.pv__empty-sub { font-size: 13px; color: var(--ink-3); line-height: 1.7; margin: 0; }
.pv__empty-generate-btn {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 12px 28px;
  background: var(--ink); color: var(--paper);
  border: none; border-radius: 24px;
  font: inherit; font-size: 14.5px; font-weight: 600;
  cursor: pointer; transition: all .15s;
  box-shadow: 0 4px 16px rgba(29,27,22,.2);
}
.pv__empty-generate-btn:hover { background: var(--accent); box-shadow: 0 6px 20px rgba(29,27,22,.25); transform: translateY(-1px); }
.pv__empty-hint { font-size: 11px; color: var(--ink-4); margin: 0; }

/* Tool message (web search) */
.pv__msg-tool { padding: 4px 0; }

/* ── Claude-style messages ── */
.pv__msg {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 6px 0;
}

/* User: right-aligned, no avatar visible */
.pv__msg--user {
  flex-direction: row-reverse;
}
.pv__msg--user .pv__msg-avatar { display: none; }  /* hide avatar for user */

/* AI avatar: small circle */
.pv__msg-avatar {
  width: 26px; height: 26px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 9px; font-weight: 700; font-family: var(--f-mono);
  background: var(--ink); color: var(--paper);
  margin-top: 2px;
}

/* Body */
.pv__msg-body { min-width: 0; max-width: 85%; }
.pv__msg--user .pv__msg-body {
  display: flex; flex-direction: column; align-items: flex-end;
  max-width: 80%;
}

/* Header: only show for AI */
.pv__msg-head { display: flex; gap: 8px; align-items: baseline; margin-bottom: 5px; }
.pv__msg--user .pv__msg-head { display: none; }   /* hide header for user */
.pv__msg-author { font-size: 12px; font-weight: 600; color: var(--ink-2); }
.pv__msg-time { font-size: 10px; color: var(--ink-4); font-family: var(--f-mono); }

/* User bubble: gray rounded pill */
.pv__msg--user .pv__msg-text {
  background: #e8e6e1;          /* warm gray, like Claude */
  color: var(--ink);
  border: none;
  border-radius: 18px 18px 4px 18px;  /* small bottom-right corner = sent feel */
  padding: 10px 16px;
  font-size: 13.5px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: break-word;
  display: block;
}

/* AI text: no bubble, clean flowing text */
.pv__msg--assistant .pv__msg-text {
  background: transparent;
  border: none;
  border-radius: 0;
  padding: 0;
  font-size: 14px;
  line-height: 1.75;
  color: var(--ink);
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: break-word;
  display: block;
}

/* system message */
.pv__msg--system .pv__msg-text {
  font-size: 12px; color: var(--ink-4);
  background: transparent; border: none; padding: 0;
  font-style: italic;
}
.pv__msg--system .pv__msg-avatar { display: none; }
.pv__msg--system .pv__msg-head { display: none; }

/* Spacing between consecutive messages */
.pv__msg + .pv__msg { margin-top: 12px; }
.pv__msg--assistant + .pv__msg--assistant { margin-top: 4px; }

/* Outline card */
.pv__moc {
  margin-top: 8px; border: 1px solid var(--rule-strong); border-radius: 8px;
  background: var(--paper); overflow: hidden; font-size: 12px;
}
.pv__moc-head { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; border-bottom: 1px solid var(--rule); }
.pv__moc-title { font-family: var(--f-serif); font-weight: 500; color: var(--ink); }
.pv__moc-stats { font-size: 11px; color: var(--ink-4); font-family: var(--f-mono); }
.pv__moc-rows { padding: 6px 0; max-height: 180px; overflow-y: auto; }
.pv__moc-row { display: flex; align-items: center; gap: 10px; padding: 4px 14px; }
.pv__moc-num { font-family: var(--f-mono); font-size: 11px; color: var(--ink-4); flex-shrink: 0; }
.pv__moc-name { flex: 1; color: var(--ink-2); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pv__moc-pages { font-family: var(--f-mono); font-size: 10.5px; color: var(--accent); }
.pv__moc-foot { padding: 6px 14px 10px; font-size: 11px; color: var(--ink-4); border-top: 1px solid var(--rule); }

/* Sources attribution card */
.pv__sources-card {
  margin-top: 8px;
  padding: 8px 12px;
  border: 1px solid var(--rule);
  border-radius: 8px;
  background: var(--paper-2);
}
.pv__sources-title {
  display: flex; align-items: center; gap: 5px;
  font-size: 11px; font-weight: 600; color: var(--ink-3);
  text-transform: uppercase; letter-spacing: .04em;
  font-family: var(--f-mono); margin-bottom: 6px;
}
.pv__sources-list { display: flex; flex-wrap: wrap; gap: 5px; }
.pv__source-tag {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 9px; border-radius: 12px;
  font-size: 11.5px; font-weight: 500;
}
.pv__source-tag--file { background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; }
.pv__source-tag--web  { background: #f0fdf4; color: #15803d; border: 1px solid #bbf7d0; }
.pv__source-tag--rag  { background: #faf5ff; color: #7e22ce; border: 1px solid #e9d5ff; }

/* Form modal */
.pv__modal-overlay {
  position: fixed; inset: 0; z-index: 200;
  background: rgba(29,27,22,.45); backdrop-filter: blur(3px);
  display: flex; align-items: center; justify-content: center; padding: 24px;
}
.pv__form-modal {
  background: var(--paper); border: 1px solid var(--rule-strong);
  border-radius: 14px; box-shadow: 0 24px 64px rgba(29,27,22,.2);
  width: 100%; max-width: 560px; max-height: 92vh;
  display: flex; flex-direction: column; overflow: hidden;
  animation: pv-modal-in .18s ease;
}
@keyframes pv-modal-in { from { transform: translateY(10px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
.pv__form-modal-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 20px 12px;
  border-bottom: 1px solid var(--rule);
  font-family: var(--f-serif); font-size: 16px; font-weight: 500; color: var(--ink);
  flex-shrink: 0;
}
.pv__form-modal-close {
  background: none; border: none; font-size: 20px; color: var(--ink-3);
  cursor: pointer; padding: 0 4px; line-height: 1;
}
.pv__form-modal-close:hover { color: var(--ink); }

/* Metadata chips */
.pv__msg-meta { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 6px; }
.pv__chip { display: inline-flex; align-items: center; gap: 4px; padding: 2px 7px; border: 1px solid var(--rule); border-radius: 4px; font-family: var(--f-mono); font-size: 10.5px; color: var(--ink-3); background: var(--paper-2); }
.pv__chip-k { color: var(--ink-4); margin-right: 2px; }
.pv__chip--time { color: var(--accent); border-color: var(--accent-stroke); background: var(--accent-soft); }
.pv__chip--quality { color: #16a34a; border-color: #86efac; background: #f0fdf4; }
.pv__chip--rag { color: #7c3aed; border-color: #c4b5fd; background: #f5f3ff; }

/* Generating typing — no background, matches AI text style */
.pv__msg--typing .pv__msg-avatar { animation: pulse-avatar 1.5s ease-in-out infinite; }
@keyframes pulse-avatar { 0%,100% { opacity: .5; } 50% { opacity: 1; } }
.pv__typing { padding: 0; }
.pv__typing-step { font-size: 13px; color: var(--ink-3); margin-bottom: 10px; }
.pv__typing-bar {
  height: 2px; background: var(--rule); border-radius: 2px;
  overflow: hidden; margin-bottom: 10px; max-width: 160px;
}
.pv__typing-bar-fill {
  height: 100%; width: 50%; background: var(--accent); border-radius: 2px;
  animation: typing-progress 1.8s ease-in-out infinite;
}
@keyframes typing-progress { 0% { transform: translateX(-100%); } 100% { transform: translateX(300%); } }

.pv__error-text {
  font-size: 12px; color: #dc2626;
  padding: 4px 24px; flex-shrink: 0;
}
.pv__adjust-hint {
  padding: 4px 24px 6px;
  font-size: 11.5px;
  color: var(--ink-4);
  flex-shrink: 0;
}
</style>
