<script setup lang="ts">
import { ref } from 'vue';

defineProps<{
  disabled?: boolean;
  loadingQuestionnaire?: boolean;
}>();

const emit = defineEmits<{
  (e: 'submit', text: string, minSlides: number, maxSlides: number): void;
}>();

const topic = ref('');
const scene = ref('商业汇报');
const audience = ref('高层管理者');
const goal = ref('信息传递');
const minSlides = ref(10);
const maxSlides = ref(18);
const style = ref('正式严谨');
const depth = ref('详细');
const constraints = ref('');

const scenes = ['商业汇报', '学术报告', '产品发布', '培训教学', '项目总结', '其他'];
const audiences = ['高层管理者', '技术团队', '普通大众', '学生', '客户', '其他'];
const goals = ['说服决策', '信息传递', '教学培训', '成果展示'];
const styles = ['正式严谨', '轻松活泼', '叙事化', '技术性'];
const depths = ['概述', '详细', '深度分析'];

function buildPrompt(): string {
  const lines = [
    `请为以下演示文稿生成PPT大纲：`,
    `【主题】${topic.value.trim()}`,
    `【使用场景】${scene.value}`,
    `【受众对象】${audience.value}`,
    `【目标结果】${goal.value}`,
    `【页数范围】${minSlides.value}–${maxSlides.value} 页`,
    `【表达风格】${style.value}`,
    `【信息深度】${depth.value}`,
  ];
  if (constraints.value.trim()) {
    lines.push(`【约束条件】${constraints.value.trim()}`);
  }
  return lines.join('\n');
}

function onSubmit() {
  if (!topic.value.trim()) return;
  emit('submit', buildPrompt(), minSlides.value, maxSlides.value);
}
</script>

<template>
  <div class="req-form">
    <div class="req-header">
      <h2>新建演示大纲</h2>
      <p>填写以下信息，帮助 AI 生成更精准的初版大纲</p>
    </div>

    <div class="req-body">
      <div class="form-field full-width">
        <label>演示主题 <span class="req-star">*</span></label>
        <input
          v-model="topic"
          type="text"
          placeholder="例如：2024 年度营销策略汇报"
          :disabled="disabled"
        />
      </div>

      <div class="form-row">
        <div class="form-field">
          <label>使用场景</label>
          <select v-model="scene" :disabled="disabled">
            <option v-for="s in scenes" :key="s">{{ s }}</option>
          </select>
        </div>
        <div class="form-field">
          <label>受众对象</label>
          <select v-model="audience" :disabled="disabled">
            <option v-for="a in audiences" :key="a">{{ a }}</option>
          </select>
        </div>
        <div class="form-field">
          <label>目标结果</label>
          <select v-model="goal" :disabled="disabled">
            <option v-for="g in goals" :key="g">{{ g }}</option>
          </select>
        </div>
      </div>

      <div class="form-row">
        <div class="form-field">
          <label>表达风格</label>
          <div class="chip-group">
            <label
              v-for="s in styles"
              :key="s"
              class="chip"
              :class="{ active: style === s, 'chip-disabled': disabled }"
            >
              <input type="radio" v-model="style" :value="s" :disabled="disabled" hidden />
              {{ s }}
            </label>
          </div>
        </div>
        <div class="form-field">
          <label>信息深度</label>
          <div class="chip-group">
            <label
              v-for="d in depths"
              :key="d"
              class="chip"
              :class="{ active: depth === d, 'chip-disabled': disabled }"
            >
              <input type="radio" v-model="depth" :value="d" :disabled="disabled" hidden />
              {{ d }}
            </label>
          </div>
        </div>
      </div>

      <div class="form-row slides-row">
        <div class="form-field slides-field">
          <label>最少页数</label>
          <input v-model.number="minSlides" type="number" min="1" max="60" :disabled="disabled" />
        </div>
        <div class="slides-sep">—</div>
        <div class="form-field slides-field">
          <label>最多页数</label>
          <input v-model.number="maxSlides" type="number" min="1" max="60" :disabled="disabled" />
        </div>
      </div>

      <div class="form-field full-width">
        <label>约束条件 <span class="opt-tag">可选</span></label>
        <textarea
          v-model="constraints"
          rows="3"
          placeholder="例如：不超过20页，需包含数据图表，避免过多技术术语..."
          :disabled="disabled"
        />
      </div>

      <button
        class="generate-btn"
        :disabled="disabled || !topic.trim()"
        @click="onSubmit"
      >
        {{ loadingQuestionnaire ? '分析需求中…' : disabled ? '生成中...' : '生成初版大纲' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.req-form {
  background: var(--paper);
  display: flex; flex-direction: column; gap: 0;
  flex: 1; overflow: hidden;
}

.req-header {
  padding: 28px 32px 20px;
  border-bottom: 1px solid var(--rule);
  background: var(--paper);
}
.req-header h2 {
  margin: 0 0 2px;
  font-family: var(--f-serif);
  font-size: 22px; font-weight: 500; letter-spacing: -0.01em;
  color: var(--ink);
}
.req-header p {
  margin: 0;
  font-size: 13px; color: var(--ink-3); line-height: 1.6;
}

.req-body {
  flex: 1; overflow-y: auto;
  padding: 20px 32px 24px;
  display: flex; flex-direction: column; gap: 16px;
}

.req-star { color: var(--accent); margin-left: 2px; }
.opt-tag { font-size: 10.5px; color: var(--ink-4); font-weight: 400; margin-left: 4px; font-family: var(--f-mono); }

.form-row { display: flex; gap: 12px; flex-wrap: wrap; }
.form-field {
  display: flex; flex-direction: column; gap: 5px;
  font-size: 13px; color: var(--ink); flex: 1; min-width: 120px;
}
.form-field.full-width { flex-basis: 100%; }
.form-field label { font-size: 12px; font-weight: 600; color: var(--ink-2); }
.form-field input, .form-field select, .form-field textarea {
  border: 1px solid var(--rule); border-radius: var(--r-sm);
  padding: 7px 10px; font: inherit; font-size: 13px;
  background: var(--paper); color: var(--ink); outline: none;
  transition: border-color .12s;
}
.form-field input:focus, .form-field select:focus, .form-field textarea:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.form-field textarea { resize: vertical; }

.chip-group { display: flex; flex-wrap: wrap; gap: 5px; }
.chip {
  padding: 4px 11px;
  border: 1px solid var(--rule); border-radius: 20px;
  font-size: 12px; cursor: pointer; user-select: none;
  background: var(--paper); color: var(--ink-2);
  transition: all .12s;
}
.chip:hover:not(.chip-disabled) { border-color: var(--accent-stroke); background: var(--accent-soft); color: var(--accent); }
.chip.active { background: var(--ink); border-color: var(--ink); color: var(--paper); }
.chip.chip-disabled { opacity: 0.45; cursor: not-allowed; }

.slides-row { align-items: flex-end; flex-wrap: nowrap; gap: 8px; }
.slides-field { flex: 0 0 90px; min-width: unset; }
.slides-field input { width: 100%; }
.slides-sep { font-size: 16px; color: var(--ink-4); padding-bottom: 6px; flex-shrink: 0; }

.generate-btn {
  align-self: flex-start;
  padding: 9px 22px;
  border: none; border-radius: var(--r);
  background: var(--ink); color: var(--paper);
  font: inherit; font-size: 13.5px; font-weight: 500;
  cursor: pointer; transition: all .15s;
  margin-top: 4px;
}
.generate-btn:hover:not(:disabled) { background: var(--accent); }
.generate-btn:disabled { opacity: 0.45; cursor: not-allowed; }
</style>
