<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import type { QuestionItem, QuestionnaireAnswer } from '@/types';

const props = defineProps<{
  questions: QuestionItem[];
  topic: string;
}>();

const emit = defineEmits<{
  submit: [answers: QuestionnaireAnswer[]];
  skip: [];
}>();

// answers keyed by questionId
const answers = reactive<Record<string, QuestionnaireAnswer>>({});
const customTexts = reactive<Record<string, string>>({});

watch(() => props.questions, () => {
  Object.keys(answers).forEach(k => delete answers[k]);
  Object.keys(customTexts).forEach(k => delete customTexts[k]);
}, { immediate: true });

function selectOption(qid: string, optId: string, optLabel: string) {
  answers[qid] = { questionId: qid, type: 'option', optionId: optId, optionLabel: optLabel };
}

function selectAiDecide(qid: string) {
  answers[qid] = { questionId: qid, type: 'ai_decide' };
}

function selectCustom(qid: string) {
  answers[qid] = { questionId: qid, type: 'custom', customText: customTexts[qid] ?? '' };
}

function onCustomInput(qid: string, val: string) {
  customTexts[qid] = val;
  answers[qid] = { questionId: qid, type: 'custom', customText: val };
}

const allAnswered = computed(() =>
  props.questions.every(q => answers[q.id] !== undefined),
);

function onSubmit() {
  if (!allAnswered.value) return;
  emit('submit', props.questions.map(q => answers[q.id]));
}

function optionLabel(id: string) {
  return id.toUpperCase();
}
</script>

<template>
  <div class="qz-overlay" @click.self="emit('skip')">
    <div class="qz-modal" role="dialog" aria-modal="true">

      <!-- Header -->
      <div class="qz-head">
        <div class="qz-head__eyebrow">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
          AI 提问
        </div>
        <h2 class="qz-head__title">在生成前，我想了解更多</h2>
        <p class="qz-head__sub">
          关于「<span class="qz-head__topic">{{ topic.length > 40 ? topic.slice(0, 40) + '…' : topic }}</span>」，回答以下问题有助于生成更精准的大纲
        </p>
      </div>

      <!-- Questions -->
      <div class="qz-body">
        <div
          v-for="(q, qi) in questions"
          :key="q.id"
          class="qz-question"
        >
          <div class="qz-q__num">{{ qi + 1 }}</div>
          <div class="qz-q__content">
            <div class="qz-q__text">{{ q.question }}</div>
            <div class="qz-options">
              <!-- A / B / C options -->
              <button
                v-for="opt in q.options"
                :key="opt.id"
                type="button"
                :class="['qz-opt', { 'is-selected': answers[q.id]?.type === 'option' && answers[q.id]?.optionId === opt.id }]"
                @click="selectOption(q.id, opt.id, opt.label)"
              >
                <span class="qz-opt__key">{{ optionLabel(opt.id) }}</span>
                <span class="qz-opt__label">{{ opt.label }}</span>
              </button>

              <!-- D: AI decide -->
              <button
                v-if="q.allow_ai_decide"
                type="button"
                :class="['qz-opt', 'qz-opt--ai', { 'is-selected': answers[q.id]?.type === 'ai_decide' }]"
                @click="selectAiDecide(q.id)"
              >
                <span class="qz-opt__key">D</span>
                <span class="qz-opt__label">由 AI 决定</span>
              </button>

              <!-- D: custom text (when allow_ai_decide is false) -->
              <div
                v-else-if="q.allow_custom"
                :class="['qz-opt', 'qz-opt--custom', { 'is-selected': answers[q.id]?.type === 'custom' }]"
                @click="selectCustom(q.id)"
              >
                <span class="qz-opt__key">D</span>
                <input
                  class="qz-custom-input"
                  :value="customTexts[q.id] ?? ''"
                  placeholder="自定义答案…"
                  @focus="selectCustom(q.id)"
                  @input="onCustomInput(q.id, ($event.target as HTMLInputElement).value)"
                  @click.stop
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="qz-foot">
        <button class="qz-skip" type="button" @click="emit('skip')">
          跳过，直接生成
        </button>
        <button
          class="qz-submit"
          type="button"
          :disabled="!allAnswered"
          @click="onSubmit"
        >
          确认并生成
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── OVERLAY ── */
.qz-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  background: rgba(29, 27, 22, 0.55);
  backdrop-filter: blur(2px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  animation: qz-fade-in 0.15s ease;
}

@keyframes qz-fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

/* ── MODAL ── */
.qz-modal {
  background: var(--paper);
  border: 1px solid var(--rule-strong);
  border-radius: 12px;
  box-shadow: 0 20px 60px rgba(29, 27, 22, 0.20), 0 4px 16px rgba(29, 27, 22, 0.10);
  max-width: 560px;
  width: 100%;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: qz-slide-up 0.18s ease;
}

@keyframes qz-slide-up {
  from { transform: translateY(12px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

/* ── HEAD ── */
.qz-head {
  padding: 24px 28px 18px;
  border-bottom: 1px solid var(--rule);
  flex-shrink: 0;
}

.qz-head__eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-family: var(--f-mono);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--accent);
  margin-bottom: 8px;
}

.qz-head__title {
  font-family: var(--f-serif);
  font-size: 20px;
  font-weight: 500;
  color: var(--ink);
  margin: 0 0 8px;
  letter-spacing: -0.01em;
  line-height: 1.25;
}

.qz-head__sub {
  font-size: 13px;
  color: var(--ink-3);
  margin: 0;
  line-height: 1.6;
}

.qz-head__topic {
  color: var(--ink);
  font-weight: 500;
}

/* ── BODY ── */
.qz-body {
  overflow-y: auto;
  flex: 1;
  padding: 20px 28px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* ── QUESTION ── */
.qz-question {
  display: grid;
  grid-template-columns: 24px 1fr;
  gap: 14px;
  align-items: flex-start;
}

.qz-q__num {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--paper-3);
  border: 1px solid var(--rule-strong);
  font-family: var(--f-mono);
  font-size: 11px;
  font-weight: 700;
  color: var(--ink-3);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 1px;
}

.qz-q__text {
  font-size: 14px;
  font-weight: 500;
  color: var(--ink);
  line-height: 1.45;
  margin-bottom: 12px;
}

/* ── OPTIONS ── */
.qz-options {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.qz-opt {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border: 1px solid var(--rule);
  border-radius: 8px;
  background: var(--paper-2);
  cursor: pointer;
  text-align: left;
  width: 100%;
  font-family: inherit;
  transition: all 0.12s;
  color: var(--ink-2);
}

.qz-opt:hover {
  background: var(--paper-3);
  border-color: var(--rule-strong);
  color: var(--ink);
}

.qz-opt.is-selected {
  background: var(--accent-soft);
  border-color: var(--accent-stroke);
  color: var(--ink);
}

.qz-opt__key {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border-radius: 5px;
  background: var(--paper-3);
  border: 1px solid var(--rule-strong);
  font-family: var(--f-mono);
  font-size: 11px;
  font-weight: 700;
  color: var(--ink-3);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.12s;
}

.qz-opt.is-selected .qz-opt__key {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--paper);
}

.qz-opt__label {
  font-size: 13px;
  line-height: 1.4;
}

/* AI decide variant */
.qz-opt--ai .qz-opt__key {
  color: var(--ink-4);
  font-style: italic;
}

.qz-opt--ai.is-selected .qz-opt__key {
  background: var(--ink-2);
  border-color: var(--ink-2);
  color: var(--paper);
  font-style: normal;
}

.qz-opt--ai.is-selected {
  background: var(--paper-3);
  border-color: var(--ink-4);
}

/* Custom input variant */
.qz-opt--custom {
  padding: 8px 14px;
}

.qz-custom-input {
  flex: 1;
  border: none;
  background: transparent;
  font: inherit;
  font-size: 13px;
  color: var(--ink);
  outline: none;
  padding: 2px 0;
}

.qz-custom-input::placeholder {
  color: var(--ink-4);
  font-style: italic;
}

/* ── FOOT ── */
.qz-foot {
  padding: 16px 28px 22px;
  border-top: 1px solid var(--rule);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-shrink: 0;
  background: var(--paper-2);
}

.qz-skip {
  font-size: 12.5px;
  color: var(--ink-4);
  background: transparent;
  border: none;
  cursor: pointer;
  font-family: inherit;
  padding: 4px 0;
  transition: color 0.12s;
}
.qz-skip:hover { color: var(--ink-2); text-decoration: underline; }

.qz-submit {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 36px;
  padding: 0 20px;
  background: var(--ink);
  color: var(--paper);
  border: 1px solid var(--ink);
  border-radius: 8px;
  font-size: 13.5px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.12s;
}
.qz-submit:hover { background: var(--accent); border-color: var(--accent); }
.qz-submit:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.qz-submit:disabled:hover { background: var(--ink); border-color: var(--ink); }
</style>
