<script setup lang="ts">
import type { ChatSession } from '@/types';

const props = defineProps<{
  sessions: ChatSession[];
  activeSessionId: string;
}>();

const emit = defineEmits<{
  create: [];
  select: [sessionId: string];
  delete: [sessionId: string];
}>();
</script>

<template>
  <aside class="sidebar">
    <div class="sidebar-header">
      <h2>会话</h2>
      <button class="ghost-btn" type="button" @click="emit('create')">+ 新建</button>
    </div>
    <ul class="session-list">
      <li
        v-for="session in props.sessions"
        :key="session.id"
        :class="['session-item', { active: session.id === props.activeSessionId }]"
        @click="emit('select', session.id)"
      >
        <div class="session-body">
          <p class="session-title">{{ session.title }}</p>
          <p class="session-meta">{{ new Date(session.updatedAt).toLocaleString() }}</p>
        </div>
        <button
          class="delete-btn"
          type="button"
          title="删除会话"
          aria-label="删除会话"
          @click.stop="emit('delete', session.id)"
        >×</button>
      </li>
    </ul>
  </aside>
</template>

<style scoped>
.session-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.session-body {
  flex: 1;
  min-width: 0;
}

.delete-btn {
  flex-shrink: 0;
  background: transparent;
  border: none;
  color: #9ca3af;
  font-size: 16px;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
  line-height: 1;
  opacity: 0;
  transition: opacity 0.15s, color 0.15s;
}

.session-item:hover .delete-btn {
  opacity: 1;
}

.delete-btn:hover {
  color: #ef4444;
}
</style>
