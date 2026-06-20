<script setup lang="ts">
import type { RequirementSpec } from '../types'

defineProps<{ spec: RequirementSpec }>()
</script>

<template>
  <section class="surface requirement-panel">
    <div class="panel-kicker">CURRENT SPEC</div>
    <h2>{{ spec.title || '需求理解尚未形成' }}</h2>
    <p class="summary">{{ spec.summary || 'Agent 完成首轮分析后将在这里展示结构化需求。' }}</p>

    <el-divider />

    <template v-if="spec.modules.length">
      <h3>模块与功能</h3>
      <div v-for="module in spec.modules" :key="module.name" class="module">
        <strong>{{ module.name }}</strong>
        <span>{{ module.description }}</span>
        <ul>
          <li v-for="feature in module.features" :key="feature.name">
            {{ feature.name }}
          </li>
        </ul>
      </div>
    </template>

    <template v-if="spec.dependencies.length">
      <h3>依赖关系</h3>
      <div class="json-list">
        <pre v-for="(item, index) in spec.dependencies" :key="index">{{ item }}</pre>
      </div>
    </template>

    <template v-if="spec.assumptions.length">
      <h3>当前假设</h3>
      <el-tag
        v-for="item in spec.assumptions"
        :key="item"
        type="warning"
        effect="plain"
        class="assumption"
      >
        {{ item }}
      </el-tag>
    </template>

    <h3>完整度</h3>
    <div class="completeness">
      <div v-for="(passed, name) in spec.completeness" :key="name">
        <span :class="{ passed }">{{ passed ? '✓' : '·' }}</span>
        {{ name }}
      </div>
    </div>
  </section>
</template>

<style scoped>
.requirement-panel {
  position: sticky;
  top: 28px;
  max-height: calc(100vh - 56px);
  padding: 24px;
  overflow: auto;
}

.panel-kicker {
  margin-bottom: 8px;
  color: #8a978f;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.14em;
}

h2 {
  margin: 0;
  font-family: Georgia, "Songti SC", serif;
  font-size: 21px;
  line-height: 1.4;
}

.summary {
  color: #6f7c75;
  font-size: 13px;
  line-height: 1.7;
}

h3 {
  margin: 22px 0 10px;
  font-size: 13px;
}

.module {
  padding: 12px 0;
  border-bottom: 1px solid #eceeea;
}

.module strong,
.module span {
  display: block;
}

.module span {
  margin-top: 5px;
  color: #7d8781;
  font-size: 12px;
}

.module ul {
  margin: 8px 0 0;
  padding-left: 18px;
  color: #526158;
  font-size: 12px;
}

.json-list pre {
  padding: 9px;
  overflow: auto;
  color: #536159;
  font-size: 10px;
  white-space: pre-wrap;
  background: #f6f7f3;
  border-radius: 8px;
}

.assumption {
  max-width: 100%;
  height: auto;
  margin: 0 6px 6px 0;
  white-space: normal;
}

.completeness {
  display: grid;
  gap: 7px;
  color: #7b857f;
  font-size: 11px;
}

.completeness span {
  display: inline-grid;
  width: 17px;
  height: 17px;
  margin-right: 6px;
  place-items: center;
  background: #eceeea;
  border-radius: 50%;
}

.completeness span.passed {
  color: #fff;
  background: #3b765a;
}
</style>
