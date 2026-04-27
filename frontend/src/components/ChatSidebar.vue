<script setup lang="ts">
import type { ChatSession } from '@/types';

const props = defineProps<{
  sessions: ChatSession[];
  activeSessionId: string;
}>();

const emit = defineEmits<{
  create: [];
  select: [sessionId: string];
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
        <p class="session-title">{{ session.title }}</p>
        <p class="session-meta">{{ new Date(session.updatedAt).toLocaleString() }}</p>
      </li>
    </ul>
  </aside>
</template>
