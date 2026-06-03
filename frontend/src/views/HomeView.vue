<script setup lang="ts">
import { computed, ref } from 'vue';
import { useChatStore } from '@/stores/chat';
import type { ChatSession } from '@/types';

const store = useChatStore();
const emit = defineEmits<{ enterProject: [sessionId: string] }>();

const showCreate = ref(false);
const newProjectName = ref('');

const sessions = computed(() => [...store.sessions].sort(
  (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
));

function relativeTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return '刚刚';
  if (m < 60) return `${m} 分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} 小时前`;
  return `${Math.floor(h / 24)} 天前`;
}

function pageCount(session: ChatSession) {
  const messages = session.messages ?? [];
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].outline) {
      return messages[i].outline!.chapters.reduce((s, c) => s + c.pages.length, 0);
    }
  }
  return 0;
}

function chapterCount(session: ChatSession) {
  const messages = session.messages ?? [];
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].outline) return messages[i].outline!.chapters.length;
  }
  return 0;
}

function openProject(id: string) {
  store.switchSession(id);
  emit('enterProject', id);
}

function deleteProject(id: string) {
  store.deleteSession(id);
}

function createProject() {
  const name = newProjectName.value.trim() || '新项目';
  store.createSession();
  const session = store.activeSession;
  if (session) {
    session.title = name.slice(0, 30);
    session.topic = name;
  }
  newProjectName.value = '';
  showCreate.value = false;
  emit('enterProject', store.activeSessionId);
}
</script>

<template>
  <div class="home">
    <!-- Header -->
    <header class="home__header">
      <div class="home__brand">
        <div class="home__brand-mark">P</div>
        <div>
          <div class="home__brand-name">PPT <em>大纲</em>智能生成</div>
          <div class="home__brand-sub">AI · RAG · 多轮对话</div>
        </div>
      </div>
      <button class="home__new-btn" @click="showCreate = true">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        新建项目
      </button>
    </header>

    <!-- Project grid -->
    <main class="home__main">
      <h2 class="home__section-title">最近的项目</h2>

      <div class="home__grid">
        <!-- New project card -->
        <div class="home__card home__card--new" @click="showCreate = true">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          <span>新建项目</span>
        </div>

        <!-- Project cards -->
        <div
          v-for="session in sessions"
          :key="session.id"
          class="home__card"
          @click="openProject(session.id)"
        >
          <div class="home__card-thumb">
            <div class="home__card-thumb-lines">
              <div v-for="i in 5" :key="i" class="home__card-thumb-line" :style="{ width: `${60 + i * 8}%`, opacity: 1 - i * 0.15 }"></div>
            </div>
          </div>
          <div class="home__card-body">
            <div class="home__card-title">{{ session.title }}</div>
            <div class="home__card-topic" v-if="session.topic">{{ session.topic }}</div>
            <div class="home__card-meta">
              <span v-if="chapterCount(session) > 0" class="home__card-badge">
                {{ chapterCount(session) }} 章 · {{ pageCount(session) }} 页
              </span>
              <span class="home__card-time">{{ relativeTime(session.updatedAt) }}</span>
            </div>
          </div>
          <button
            class="home__card-del"
            title="删除项目"
            @click.stop="deleteProject(session.id)"
          >×</button>
        </div>
      </div>

      <p v-if="sessions.length === 0" class="home__empty">
        还没有项目，点击「新建项目」开始创建
      </p>
    </main>

    <!-- Create project modal — just a name -->
    <Teleport to="body">
      <div v-if="showCreate" class="home__overlay" @click.self="showCreate = false">
        <div class="home__create-modal home__create-modal--simple">
          <div class="home__create-head">
            <span>新建 PPT 项目</span>
            <button class="home__create-close" @click="showCreate = false">×</button>
          </div>
          <div class="home__create-body">
            <label class="home__create-label">项目名称</label>
            <input
              v-model="newProjectName"
              class="home__create-input"
              placeholder="例如：2024 年度营销策略汇报"
              autofocus
              @keydown.enter="createProject"
            />
            <p class="home__create-hint">进入项目后可上传文件、选择知识库、搜索网络来源，再生成大纲</p>
            <button class="home__create-btn" @click="createProject">
              创建项目 →
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.home {
  min-height: 100vh;
  background: var(--paper);
  display: flex;
  flex-direction: column;
}

.home__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 36px;
  border-bottom: 1px solid var(--rule);
  background: var(--paper);
  position: sticky;
  top: 0;
  z-index: 10;
}

.home__brand { display: flex; align-items: center; gap: 12px; }
.home__brand-mark {
  width: 36px; height: 36px; border-radius: 8px;
  background: var(--ink); color: var(--paper);
  display: flex; align-items: center; justify-content: center;
  font-family: var(--f-serif); font-size: 18px; font-weight: 700;
}
.home__brand-name {
  font-family: var(--f-serif); font-size: 17px; font-weight: 500; color: var(--ink);
}
.home__brand-name em { color: var(--accent); font-style: normal; }
.home__brand-sub { font-size: 11px; color: var(--ink-4); margin-top: 1px; }

.home__new-btn {
  display: inline-flex; align-items: center; gap: 6px;
  height: 36px; padding: 0 18px;
  background: var(--ink); color: var(--paper);
  border: none; border-radius: 8px;
  font: inherit; font-size: 13px; font-weight: 500;
  cursor: pointer; transition: background .15s;
}
.home__new-btn:hover { background: var(--accent); }

.home__main { flex: 1; padding: 32px 36px; max-width: 1100px; width: 100%; margin: 0 auto; }

.home__section-title {
  font-family: var(--f-serif); font-size: 14px; font-weight: 500;
  color: var(--ink-3); margin: 0 0 20px; letter-spacing: 0.02em;
}

.home__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
}

.home__card {
  position: relative;
  border: 1px solid var(--rule);
  border-radius: 10px;
  background: var(--paper);
  cursor: pointer;
  transition: all .15s;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.home__card:hover {
  border-color: var(--rule-strong);
  box-shadow: 0 4px 16px rgba(29,27,22,.08);
  transform: translateY(-2px);
}

.home__card--new {
  border: 1.5px dashed var(--rule-strong);
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 40px 20px;
  color: var(--ink-4);
  font-size: 13px;
  background: var(--paper-2);
  flex-direction: column;
}
.home__card--new:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-soft); }

.home__card-thumb {
  height: 120px;
  background: linear-gradient(135deg, var(--paper-3) 0%, var(--paper-2) 100%);
  padding: 16px;
  border-bottom: 1px solid var(--rule);
  display: flex;
  align-items: flex-end;
}
.home__card-thumb-lines { width: 100%; display: flex; flex-direction: column; gap: 6px; }
.home__card-thumb-line {
  height: 5px; border-radius: 3px; background: var(--rule-strong);
}

.home__card-body { padding: 14px 14px 12px; flex: 1; }
.home__card-title {
  font-size: 13.5px; font-weight: 600; color: var(--ink);
  line-height: 1.35; margin-bottom: 4px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.home__card-topic {
  font-size: 11.5px; color: var(--ink-3); margin-bottom: 8px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.home__card-meta {
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px;
}
.home__card-badge {
  font-size: 10.5px; font-family: var(--f-mono); color: var(--accent);
  background: var(--accent-soft); border: 1px solid var(--accent-stroke);
  padding: 1px 6px; border-radius: 4px;
}
.home__card-time { font-size: 11px; color: var(--ink-4); }

.home__card-del {
  position: absolute; top: 8px; right: 8px;
  width: 22px; height: 22px; border-radius: 50%;
  border: none; background: var(--paper-3); color: var(--ink-3);
  font-size: 14px; cursor: pointer; opacity: 0; transition: opacity .15s;
  display: flex; align-items: center; justify-content: center;
}
.home__card:hover .home__card-del { opacity: 1; }
.home__card-del:hover { background: #fee2e2; color: #dc2626; }

.home__empty { color: var(--ink-4); font-size: 13px; margin: 40px 0; text-align: center; }

/* Modal */
.home__overlay {
  position: fixed; inset: 0; z-index: 200;
  background: rgba(29,27,22,.5); backdrop-filter: blur(3px);
  display: flex; align-items: center; justify-content: center; padding: 24px;
}
.home__create-modal {
  background: var(--paper); border: 1px solid var(--rule-strong);
  border-radius: 14px; box-shadow: 0 24px 64px rgba(29,27,22,.2);
  width: 100%; max-width: 560px; max-height: 90vh;
  display: flex; flex-direction: column; overflow: hidden;
  animation: modal-in .18s ease;
}
@keyframes modal-in {
  from { transform: translateY(12px); opacity: 0; }
  to   { transform: translateY(0); opacity: 1; }
}
.home__create-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 24px 14px;
  border-bottom: 1px solid var(--rule);
  font-family: var(--f-serif); font-size: 16px; font-weight: 500; color: var(--ink);
}
.home__create-close {
  background: none; border: none; font-size: 20px; color: var(--ink-3);
  cursor: pointer; line-height: 1; padding: 0 4px;
}
.home__create-close:hover { color: var(--ink); }

.home__create-modal--simple { max-width: 440px; }
.home__create-body { padding: 20px 24px 24px; display: flex; flex-direction: column; gap: 10px; }
.home__create-label { font-size: 12.5px; font-weight: 600; color: var(--ink-2); }
.home__create-input {
  border: 1.5px solid var(--rule-strong); border-radius: 8px;
  padding: 10px 14px; font: inherit; font-size: 14px;
  background: var(--paper); color: var(--ink); outline: none;
  transition: border-color .15s;
}
.home__create-input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.home__create-hint { font-size: 11.5px; color: var(--ink-4); line-height: 1.6; margin: 0; }
.home__create-btn {
  align-self: flex-end; height: 38px; padding: 0 22px;
  background: var(--ink); color: var(--paper); border: none; border-radius: 8px;
  font: inherit; font-size: 13.5px; font-weight: 500; cursor: pointer; transition: background .15s;
}
.home__create-btn:hover { background: var(--accent); }
</style>
