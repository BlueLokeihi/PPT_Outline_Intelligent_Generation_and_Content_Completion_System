<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import ChatSidebar from '@/components/ChatSidebar.vue';
import PdfUploader from '@/components/PdfUploader.vue';
import ChatComposer from '@/components/ChatComposer.vue';
import RequirementsForm from '@/components/RequirementsForm.vue';
import OutlinePanel from '@/components/OutlinePanel.vue';
import { getCorpora, getRuntimeInfo, pingBridge } from '@/services/bridge';
import { useChatStore } from '@/stores/chat';
import type { OutlineResult, RagCorpusInfo } from '@/types';

const store = useChatStore();

const bridgeStatus = ref('正在检测桥接状态...');
const availableProviders = ref<string[]>(['qwen', 'glm', 'deepseek']);
const availableStrategies = ref<Array<'baseline' | 'few_shot' | 'cot_silent'>>(['baseline', 'few_shot', 'cot_silent']);
const availableCorpora = ref<RagCorpusInfo[]>([]);
const generatingSeconds = ref(0);
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

function onPdfExtracted(payload: { fileName: string; text: string }) {
  store.setPdfContext(activeSession.value.id, payload.fileName, payload.text);
}

async function onFormSubmit(text: string, minSlides: number, maxSlides: number) {
  store.minSlides = minSlides;
  store.maxSlides = maxSlides;
  await store.sendUserMessage(text);
}

async function onSend(text: string) {
  await store.sendUserMessage(text);
}

onMounted(async () => {
  const [ping, runtime, corpora] = await Promise.all([pingBridge(), getRuntimeInfo(), getCorpora()]);
  bridgeStatus.value = ping.ok ? '桥接已连接' : `桥接未连接：${ping.message}`;

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
    if (!store.corpusId) {
      store.corpusId = corpora.corpora[0].id;
    }
  }
});

watch(isGenerating, (running) => {
  if (running) {
    generatingSeconds.value = 0;
    if (generatingTimer) clearInterval(generatingTimer);
    generatingTimer = setInterval(() => {
      generatingSeconds.value += 1;
    }, 1000);
    return;
  }
  if (generatingTimer) {
    clearInterval(generatingTimer);
    generatingTimer = null;
  }
});

onBeforeUnmount(() => {
  if (generatingTimer) {
    clearInterval(generatingTimer);
    generatingTimer = null;
  }
});
</script>

<template>
  <main class="app-shell">
    <ChatSidebar
      :sessions="store.sessions"
      :active-session-id="store.activeSessionId"
      @create="store.createSession"
      @select="store.switchSession"
    />

    <section class="main-panel">
      <header class="toolbar">
        <div class="toolbar-title">
          <h1>PPT大纲原型</h1>
          <p>{{ bridgeStatus }}</p>
        </div>

        <div class="toolbar-controls">
          <label>
            Provider
            <select v-model="store.provider">
              <option v-for="provider in availableProviders" :key="provider" :value="provider">{{ provider }}</option>
            </select>
          </label>

          <label>
            Strategy
            <select v-model="store.strategy">
              <option v-for="item in availableStrategies" :key="item" :value="item">{{ item }}</option>
            </select>
          </label>

          <label>
            Schema
            <select v-model="store.schema">
              <option value="on">on</option>
              <option value="off">off</option>
            </select>
          </label>

          <label class="rag-toggle" :class="{ disabled: availableCorpora.length === 0 }">
            <input type="checkbox" v-model="store.useRag" :disabled="availableCorpora.length === 0" />
            <span>RAG增强</span>
          </label>

          <label v-if="store.useRag" class="rag-corpus">
            知识库
            <select v-model="store.corpusId" :disabled="availableCorpora.length === 0">
              <option v-if="availableCorpora.length === 0" value="">(尚无)</option>
              <option v-for="c in availableCorpora" :key="c.id" :value="c.id">
                {{ c.id }} · {{ c.size }}块
              </option>
            </select>
          </label>

          <label v-if="store.useRag" class="rag-mode">
            模式
            <select v-model="store.ragMode">
              <option value="hybrid">hybrid</option>
              <option value="vector">vector</option>
              <option value="bm25">bm25</option>
            </select>
          </label>
        </div>
      </header>

      <div class="content-grid">
        <section class="chat-board">
          <!-- Phase 1: requirements form shown for new sessions -->
          <RequirementsForm
            v-if="!hasUserMessages"
            :disabled="isGenerating"
            @submit="onFormSubmit"
          />

          <!-- Phase 2: chat view after first submission -->
          <template v-else>
            <div class="messages" ref="messagesEl">
              <article
                v-for="message in activeSession.messages"
                :key="message.id"
                :class="['message', message.role]"
              >
                <header>
                  <span>{{ message.role }}</span>
                  <span>{{ new Date(message.createdAt).toLocaleTimeString() }}</span>
                </header>
                <p>{{ message.text }}</p>

                <div v-if="message.metadata" class="meta-row">
                  <span>{{ message.metadata.provider }}</span>
                  <span>{{ message.metadata.strategy }}</span>
                  <span>{{ message.metadata.schema }}</span>
                  <span v-if="message.metadata.elapsedS">{{ message.metadata.elapsedS.toFixed(2) }}s</span>
                </div>
              </article>

              <article v-if="isGenerating" class="message assistant generating">
                <header>
                  <span>assistant</span>
                  <span>{{ generatingSeconds }}s</span>
                </header>
                <p>已触发后端生成，正在整理大纲内容，请稍候...</p>
                <div class="typing-dots" aria-hidden="true">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </article>
            </div>

            <p v-if="activeSession.lastError" class="error-text">{{ activeSession.lastError }}</p>

            <div class="adjust-hint" v-if="latestOutline && !isGenerating">
              <span>💬 在下方输入修改意见，即可调整当前大纲</span>
            </div>

            <ChatComposer :disabled="isGenerating" @send="onSend" />
          </template>
        </section>

        <aside class="aux-panel">
          <PdfUploader @extracted="onPdfExtracted" />
          <OutlinePanel :outline="latestOutline" />
        </aside>
      </div>
    </section>
  </main>
</template>
