<script setup lang="ts">
import { ref } from 'vue';

defineProps<{
  disabled?: boolean;
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
      {{ disabled ? '生成中...' : '生成初版大纲' }}
    </button>
  </div>
</template>

<style scoped>
.req-form {
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid #dbeafe;
  border-radius: 16px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  flex: 1;
  overflow: auto;
}

.req-header h2 {
  margin: 0;
  font-size: 18px;
  color: #1e3a5f;
}

.req-header p {
  margin: 6px 0 0;
  font-size: 13px;
  color: #6b7280;
}

.req-star {
  color: #ef4444;
}

.opt-tag {
  font-size: 11px;
  color: #9ca3af;
  font-weight: normal;
  margin-left: 4px;
}

.form-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  color: #374151;
  flex: 1;
  min-width: 120px;
}

.form-field.full-width {
  flex-basis: 100%;
}

.form-field label {
  font-weight: 600;
  font-size: 13px;
}

.form-field input,
.form-field select,
.form-field textarea {
  border: 1px solid #c7d2fe;
  border-radius: 8px;
  padding: 8px 10px;
  font: inherit;
  background: #fff;
  transition: border-color 0.15s;
}

.form-field input:focus,
.form-field select:focus,
.form-field textarea:focus {
  outline: none;
  border-color: #6366f1;
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.15);
}

.form-field textarea {
  resize: vertical;
}

.chip-group {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip {
  padding: 5px 12px;
  border: 1px solid #c7d2fe;
  border-radius: 20px;
  font-size: 12px;
  cursor: pointer;
  user-select: none;
  background: #f8fafc;
  color: #374151;
  transition: all 0.15s;
}

.chip:hover:not(.chip-disabled) {
  border-color: #818cf8;
  background: #eef2ff;
}

.chip.active {
  background: #6366f1;
  border-color: #6366f1;
  color: #fff;
}

.chip.chip-disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.slides-row {
  align-items: center;
  flex-wrap: nowrap;
}

.slides-field {
  flex: 0 0 100px;
  min-width: unset;
}

.slides-field input {
  width: 100%;
}

.slides-sep {
  font-size: 18px;
  color: #9ca3af;
  padding-top: 20px;
  flex-shrink: 0;
}

.generate-btn {
  align-self: flex-end;
  padding: 10px 24px;
  border: none;
  border-radius: 10px;
  background: linear-gradient(120deg, #4f46e5 0%, #0ea5e9 100%);
  color: #fff;
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s, transform 0.1s;
}

.generate-btn:hover:not(:disabled) {
  opacity: 0.9;
  transform: translateY(-1px);
}

.generate-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
  transform: none;
}
</style>
