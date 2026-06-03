<script setup lang="ts">
import { ref } from 'vue';
import HomeView from '@/views/HomeView.vue';
import ProjectView from '@/views/ProjectView.vue';
import { useChatStore } from '@/stores/chat';

const store = useChatStore();
const currentView = ref<'home' | 'project'>('home');

function enterProject(sessionId: string) {
  store.switchSession(sessionId);
  currentView.value = 'project';
}

function goHome() {
  currentView.value = 'home';
}
</script>

<template>
  <HomeView v-if="currentView === 'home'" @enter-project="enterProject" />
  <ProjectView v-else @go-home="goHome" />
</template>
