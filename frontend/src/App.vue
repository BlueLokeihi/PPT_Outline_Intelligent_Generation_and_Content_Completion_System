<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import ChatSidebar from '@/components/ChatSidebar.vue';
import ChatComposer from '@/components/ChatComposer.vue';
import RequirementsForm from '@/components/RequirementsForm.vue';
import OutlinePanel from '@/components/OutlinePanel.vue';
import DynamicQuestionnaire from '@/components/DynamicQuestionnaire.vue';
import { getCorpora, getRuntimeInfo, pingBridge, requestQuestionnaire } from '@/services/bridge';
import { useChatStore } from '@/stores/chat';
import type { OutlineResult, QuestionItem, QuestionnaireAnswer, RagCorpusInfo } from '@/types';

const store = useChatStore();

const messagesEl = ref<HTMLDivElement | null>(null);
const bridgeOk = ref(false);
const bridgeMsg = ref('检测中…');
const availableProviders = ref<string[]>(['qwen', 'glm', 'deepseek']);
const availableStrategies = ref<Array<'baseline' | 'few_shot' | 'cot_silent'>>(['baseline', 'few_shot', 'cot_silent']);
const availableCorpora = ref<RagCorpusInfo[]>([]);
const generatingSeconds = ref(0);
const outlineVisible = ref(true);
const viewMode = ref<'doc' | 'cards' | 'slides'>('doc');

// ── Questionnaire state ────────────────────────────────────────────────
const questionnaireLoading = ref(false);
const showQuestionnaire = ref(false);
const questionnaireItems = ref<QuestionItem[]>([]);
const pendingMessage = ref('');
const pendingMinSlides = ref(10);
const pendingMaxSlides = ref(18);
let generatingTimer: ReturnType<typeof setInterval> | null = null;

const activeSession = computed(() => store.activeSession);
const isGenerating = computed(() => activeSession.value?.status === 'running');

const hasUserMessages = computed(() =>
  activeSession.value?.messages.some((m) => m.role === 'user') ?? false,
);

const latestOutline = computed((): OutlineResult | null => {
  const messages = activeSession.value?.messages ?? [];
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].outline) return messages[i].outline!;
  }
  return null;
});

const editableOutline = computed(() => activeSession.value?.editableOutline ?? latestOutline.value);

function roleLabel(role: string) {
  if (role === 'user') return '用户';
  if (role === 'assistant') return 'AI';
  return 'sys';
}

function outlinePageCount(outline: OutlineResult): number {
  return outline.chapters.reduce((s, ch) => s + ch.pages.length, 0);
}

const suggestions = computed((): string[] => {
  if (!latestOutline.value || isGenerating.value) return [];
  const chs = latestOutline.value.chapters;
  const result: string[] = [];
  if (chs.length > 0) {
    const mid = chs[Math.floor(chs.length / 2)];
    result.push(`细化「${mid.title}」，补充数据与案例`);
  }
  if (chs.length >= 2) {
    result.push(`将「${chs[chs.length - 1].title}」拆为两个独立章节`);
  }
  result.push('在开头增加执行摘要（1页）');
  const total = outlinePageCount(latestOutline.value);
  result.push(`压缩总页数，控制在 ${Math.max(8, total - 2)} 页以内`);
  return result.slice(0, 4);
});

function onPdfExtracted(payload: { fileName: string; text: string; pageCount?: number }) {
  store.setPdfContext(activeSession.value.id, payload.fileName, payload.text);
}

function onCorporaUpdated(list: RagCorpusInfo[]) {
  availableCorpora.value = list;
  if (!store.corpusId && list.length > 0) store.corpusId = list[0].id;
}

async function onFormSubmit(text: string, minSlides: number, maxSlides: number) {
  store.minSlides = minSlides;
  store.maxSlides = maxSlides;
  pendingMinSlides.value = minSlides;
  pendingMaxSlides.value = maxSlides;
  pendingMessage.value = text;

  questionnaireLoading.value = true;
  try {
    const result = await requestQuestionnaire(text, store.provider);
    if (result.ok && result.needs_questionnaire && result.questions?.length > 0) {
      questionnaireItems.value = result.questions;
      showQuestionnaire.value = true;
      return; // wait for questionnaire
    }
  } catch {
    // If questionnaire fails, proceed directly
  } finally {
    questionnaireLoading.value = false;
  }
  await store.sendUserMessage(text);
}

function formatQuestionnaireAnswers(answers: QuestionnaireAnswer[], questions: QuestionItem[]): string {
  const lines = ['[问卷答案]'];
  for (const ans of answers) {
    const q = questions.find(x => x.id === ans.questionId);
    if (!q) continue;
    lines.push(`Q: ${q.question}`);
    if (ans.type === 'option') {
      const opt = q.options.find(o => o.id === ans.optionId);
      lines.push(`A: ${ans.optionId?.toUpperCase()} — ${opt?.label ?? ans.optionLabel}`);
    } else if (ans.type === 'custom') {
      lines.push(`A: 自定义 — ${ans.customText}`);
    } else {
      lines.push('A: 由 AI 决定');
    }
  }
  return lines.join('\n');
}

async function onQuestionnaireSubmit(answers: QuestionnaireAnswer[]) {
  showQuestionnaire.value = false;
  const answerBlock = formatQuestionnaireAnswers(answers, questionnaireItems.value);
  const enrichedMessage = `${pendingMessage.value}\n\n${answerBlock}`;
  await store.sendUserMessage(enrichedMessage);
}

async function onQuestionnaireSkip() {
  showQuestionnaire.value = false;
  await store.sendUserMessage(pendingMessage.value);
}

async function onSend(text: string) {
  await store.sendUserMessage(text);
}

onMounted(async () => {
  const [ping, runtime, corpora] = await Promise.all([pingBridge(), getRuntimeInfo(), getCorpora()]);
  bridgeOk.value = ping.ok;
  bridgeMsg.value = ping.ok ? '已连接' : '未连接';

  if (runtime.ok) {
    if (runtime.providers.length > 0) {
      availableProviders.value = runtime.providers;
      if (!runtime.providers.includes(store.provider)) {
        store.provider = runtime.providers[0] ?? 'qwen';
      }
    }
    if (runtime.strategies.length > 0) {
      availableStrategies.value = runtime.strategies as Array<'baseline' | 'few_shot' | 'cot_silent'>;
      if (!runtime.strategies.includes(store.strategy)) {
        store.strategy = (runtime.strategies[0] as 'baseline' | 'few_shot' | 'cot_silent') ?? 'baseline';
      }
    }
  }

  if (corpora.ok && corpora.corpora.length > 0) {
    availableCorpora.value = corpora.corpora;
    if (!store.corpusId) store.corpusId = corpora.corpora[0].id;
  }
});

watch(
  () => activeSession.value?.messages.length,
  () => {
    nextTick(() => {
      if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight;
    });
  },
);

watch(isGenerating, (running) => {
  if (running) {
    generatingSeconds.value = 0;
    if (generatingTimer) clearInterval(generatingTimer);
    generatingTimer = setInterval(() => { generatingSeconds.value += 1; }, 1000);
    return;
  }
  if (generatingTimer) { clearInterval(generatingTimer); generatingTimer = null; }
});

onBeforeUnmount(() => {
  if (generatingTimer) { clearInterval(generatingTimer); generatingTimer = null; }
});
</script>

<template>
  <div class="app">
    <!-- ── Sidebar ── -->
    <ChatSidebar
      :sessions="store.sessions"
      :active-session-id="store.activeSessionId"
      :bridge-ok="bridgeOk"
      :bridge-msg="bridgeMsg"
      :provider="store.provider"
      @create="store.createSession"
      @select="store.switchSession"
      @delete="store.deleteSession"
      @pdf-extracted="onPdfExtracted"
      @corpora-updated="onCorporaUpdated"
    />

    <!-- ── Main ── -->
    <div class="main">
      <!-- Topbar -->
      <header class="topbar">
        <div class="topbar__left">
          <span class="topbar__title">PPT 大纲智能生成</span>
          <span class="topbar__status">
            <span :class="['sb__foot-dot', bridgeOk ? '' : 'sb__foot-dot--err']"></span>
            {{ bridgeMsg }}
          </span>
        </div>

        <div class="topbar__controls">
          <div class="topbar__field">
            <label>模型</label>
            <select class="topbar__select" v-model="store.provider">
              <option v-for="p in availableProviders" :key="p" :value="p">{{ p }}</option>
            </select>
          </div>
          <div class="topbar__sep"></div>
          <div class="topbar__field">
            <label>策略</label>
            <select class="topbar__select" v-model="store.strategy">
              <option v-for="s in availableStrategies" :key="s" :value="s">{{ s }}</option>
            </select>
          </div>
          <div class="topbar__sep"></div>
          <div class="topbar__field">
            <label>Schema</label>
            <select class="topbar__select" v-model="store.schema">
              <option value="on">on</option>
              <option value="off">off</option>
            </select>
          </div>
          <div class="topbar__sep"></div>
          <label class="topbar__rag-toggle">
            <input type="checkbox" v-model="store.useRag" :disabled="availableCorpora.length === 0" />
            RAG
          </label>
          <template v-if="store.useRag">
            <select class="topbar__select" v-model="store.corpusId" :disabled="availableCorpora.length === 0">
              <option v-if="availableCorpora.length === 0" value="">(无知识库)</option>
              <option v-for="c in availableCorpora" :key="c.id" :value="c.id">{{ c.id }}</option>
            </select>
            <select class="topbar__select" v-model="store.ragMode">
              <option value="hybrid">hybrid</option>
              <option value="vector">vector</option>
              <option value="bm25">bm25</option>
            </select>
          </template>
          <div class="topbar__sep"></div>
          <template v-if="latestOutline && outlineVisible">
            <div class="topbar__view-tabs">
              <button
                v-for="m in (['doc', 'cards', 'slides'] as const)"
                :key="m"
                :class="['topbar__view-tab', { active: viewMode === m }]"
                @click="viewMode = m"
              >{{ m === 'doc' ? 'Doc' : m === 'cards' ? 'Cards' : 'Slides' }}</button>
            </div>
            <div class="topbar__sep"></div>
          </template>
          <button class="topbar__view-btn" @click="outlineVisible = !outlineVisible">
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
              <rect x="1" y="1" width="11" height="11" rx="2" stroke="currentColor" stroke-width="1.2"/>
              <path d="M8.5 1v11" stroke="currentColor" stroke-width="1.2"/>
            </svg>
            {{ outlineVisible ? '折叠大纲' : '展开大纲' }}
          </button>
        </div>
      </header>

      <!-- Workspace -->
      <div class="workspace" :class="{ 'outline-hidden': !outlineVisible }">
        <!-- Chat column -->
        <div class="workspace__chat">
          <!-- Phase 1: wizard form -->
          <RequirementsForm
            v-if="!hasUserMessages"
            :disabled="isGenerating || questionnaireLoading"
            :loading-questionnaire="questionnaireLoading"
            @submit="onFormSubmit"
          />

          <!-- Phase 2: chat -->
          <template v-else>
            <div class="chat">
              <div class="chat__scroll" ref="messagesEl">
                <div class="chat__inner">
                  <template v-for="message in activeSession.messages" :key="message.id">
                    <div
                      v-if="message.role !== 'system' || message.text.startsWith('已载入')"
                      :class="['msg', `msg--${message.role}`]"
                    >
                      <div class="msg__avatar">{{ roleLabel(message.role) }}</div>
                      <div class="msg__body">
                        <div class="msg__head">
                          <span class="msg__author">
                            {{ message.role === 'user' ? '用户' : message.role === 'assistant' ? '智能大纲' : '系统' }}
                          </span>
                          <span class="msg__time">{{ new Date(message.createdAt).toLocaleTimeString() }}</span>
                        </div>
                        <div class="msg__content">
                          <p class="msg__text">{{ message.text }}</p>
                          <div v-if="message.role === 'assistant' && message.outline" class="msg__outline-card">
                            <div class="moc__head">
                              <span class="moc__title">{{ message.outline.title }}</span>
                              <span class="moc__stats">{{ message.outline.chapters.length }} 章 · {{ outlinePageCount(message.outline) }} 页</span>
                            </div>
                            <div class="moc__rows">
                              <div v-for="(ch, i) in message.outline.chapters" :key="i" class="moc__row">
                                <span class="moc__num">{{ String(i + 1).padStart(2, '0') }}</span>
                                <span class="moc__name">{{ ch.title }}</span>
                                <span class="moc__pages">{{ ch.pages.length }}p</span>
                              </div>
                            </div>
                            <div class="moc__foot">在右侧大纲面板中查看完整结构 →</div>
                          </div>
                        </div>
                        <div v-if="message.metadata" class="msg__meta">
                          <span v-if="message.metadata.provider" class="meta-chip">
                            <span class="meta-chip-k">provider</span>{{ message.metadata.provider }}
                          </span>
                          <span v-if="message.metadata.strategy" class="meta-chip">
                            <span class="meta-chip-k">strategy</span>{{ message.metadata.strategy }}
                          </span>
                          <span v-if="message.metadata.elapsedS" class="meta-chip meta-chip--time">
                            {{ message.metadata.elapsedS.toFixed(2) }}s
                          </span>
                          <span v-if="message.metadata.quality" class="meta-chip meta-chip--quality">
                            Q {{ message.metadata.quality.overall_score_0_100 }}
                          </span>
                          <span v-if="message.metadata.rag?.used" class="meta-chip meta-chip--rag">
                            RAG ✓
                          </span>
                        </div>
                      </div>
                    </div>
                  </template>

                  <!-- Generating bubble -->
                  <div v-if="isGenerating" class="msg msg--assistant msg--typing">
                    <div class="msg__avatar">AI</div>
                    <div class="msg__body">
                      <div class="msg__head">
                        <span class="msg__author">智能大纲</span>
                        <span class="msg__time">{{ generatingSeconds }}s</span>
                      </div>
                      <div class="msg__typing">
                        <div class="msg__typing-step">正在生成大纲结构…</div>
                        <div class="msg__typing-bar"><div class="msg__typing-bar-fill"></div></div>
                        <div class="typing-dots"><span></span><span></span><span></span></div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <p v-if="activeSession.lastError" class="error-text">{{ activeSession.lastError }}</p>

              <div class="adjust-hint" v-if="latestOutline && !isGenerating">
                继续输入修改意见以调整大纲
              </div>

              <ChatComposer :disabled="isGenerating" :suggestions="suggestions" @send="onSend" />
            </div>
          </template>
        </div>

        <!-- Outline column -->
        <div v-show="outlineVisible" class="workspace__outline">
          <OutlinePanel :outline="editableOutline" :view-mode="viewMode" />
        </div>
      </div>
    </div>
  </div>

  <!-- ── Dynamic Questionnaire Modal ── -->
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
