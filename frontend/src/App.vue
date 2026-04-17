<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import ChatSidebar from '@/components/ChatSidebar.vue';
import PdfUploader from '@/components/PdfUploader.vue';
import ChatComposer from '@/components/ChatComposer.vue';
import { getRuntimeInfo, pingBridge } from '@/services/bridge';
import { useChatStore } from '@/stores/chat';

const store = useChatStore();

const bridgeStatus = ref('正在检测桥接状态...');
const availableProviders = ref<string[]>(['qwen', 'glm', 'deepseek']);
const availableStrategies = ref<Array<'baseline' | 'few_shot' | 'cot_silent'>>(['baseline', 'few_shot', 'cot_silent']);
const generatingSeconds = ref(0);
let generatingTimer: ReturnType<typeof setInterval> | null = null;

const activeSession = computed(() => store.activeSession);
const isGenerating = computed(() => activeSession.value?.status === 'running');

function onPdfExtracted(payload: { fileName: string; text: string }) {
  store.setPdfContext(activeSession.value.id, payload.fileName, payload.text);
}

async function onSend(text: string) {
  await store.sendUserMessage(text);
}

onMounted(async () => {
  const [ping, runtime] = await Promise.all([pingBridge(), getRuntimeInfo()]);
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
});

watch(isGenerating, (running) => {
  if (running) {
    generatingSeconds.value = 0;
    if (generatingTimer) {
      clearInterval(generatingTimer);
    }
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

          <label>
            Min
            <input v-model.number="store.minSlides" type="number" min="1" max="60" />
          </label>

          <label>
            Max
            <input v-model.number="store.maxSlides" type="number" min="1" max="60" />
          </label>
        </div>
      </header>

      <div class="content-grid">
        <section class="chat-board">
          <div class="messages">
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

              <div v-if="message.outline" class="outline-preview">
                <h3>{{ message.outline.title }}</h3>
                <div v-for="chapter in message.outline.chapters" :key="chapter.title" class="chapter">
                  <h4>{{ chapter.title }}</h4>
                  <ul>
                    <li v-for="page in chapter.pages" :key="page.title">{{ page.title }}</li>
                  </ul>
                </div>
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
          <ChatComposer :disabled="isGenerating" @send="onSend" />
        </section>

        <aside class="aux-panel">
          <PdfUploader @extracted="onPdfExtracted" />

          <section class="context-card">
            <h3>当前PDF上下文</h3>
            <p class="subtle">文件：{{ activeSession.pdfName || '未上传' }}</p>
            <textarea :value="activeSession.pdfText" readonly rows="14" />
          </section>
        </aside>
      </div>
    </section>
  </main>
</template>
