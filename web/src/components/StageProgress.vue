<script setup lang="ts">
import { computed } from 'vue'
import { stageIndex, stages } from '../stages'
import type { Stage } from '../types'

const props = defineProps<{
  stage: Stage
  status: string
}>()

const active = computed(() => Math.max(stageIndex(props.stage), 0))
</script>

<template>
  <div class="stage-progress surface">
    <div
      v-for="(item, index) in stages"
      :key="item.key"
      class="stage-node"
      :class="{
        done: index < active || stage === 'COMPLETED',
        active: index === active && stage !== 'COMPLETED',
        failed: index === active && status === 'failed',
      }"
    >
      <div class="node-marker">{{ index + 1 }}</div>
      <div class="node-label">{{ item.label }}</div>
      <div v-if="index < stages.length - 1" class="node-line" />
    </div>
  </div>
</template>

<style scoped>
.stage-progress {
  display: grid;
  grid-template-columns: repeat(9, 1fr);
  padding: 20px 22px;
  overflow: hidden;
}

.stage-node {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
  color: #9ba49f;
  font-size: 11px;
  text-align: center;
}

.node-marker {
  position: relative;
  z-index: 2;
  display: grid;
  width: 27px;
  height: 27px;
  place-items: center;
  background: #eef0eb;
  border: 1px solid #d9ddd7;
  border-radius: 50%;
}

.node-line {
  position: absolute;
  top: 13px;
  left: calc(50% + 17px);
  z-index: 1;
  width: calc(100% - 34px);
  height: 1px;
  background: #dfe2dd;
}

.done,
.active {
  color: #244936;
}

.done .node-marker {
  color: #fff;
  background: #2d684e;
  border-color: #2d684e;
}

.done .node-line {
  background: #7da98d;
}

.active .node-marker {
  color: #203527;
  font-weight: 700;
  background: #d7f06f;
  border-color: #b8d35b;
  box-shadow: 0 0 0 5px rgba(215, 240, 111, 0.25);
}

.failed .node-marker {
  color: #fff;
  background: #b94747;
  border-color: #b94747;
  box-shadow: 0 0 0 5px rgba(185, 71, 71, 0.14);
}
</style>
