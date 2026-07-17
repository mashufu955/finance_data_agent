<template>
  <div class="app-container">
    <!-- 顶部导航栏 -->
    <header class="app-header">
      <div class="header-left">
        <div class="logo">
          <span class="logo-icon">🏦</span>
          <span class="logo-text">Finance Data Agent</span>
        </div>
      </div>
      <nav class="header-nav">
        <button
          :class="['nav-tab', { active: activeTab === 'overview' }]"
          @click="activeTab = 'overview'"
        >
          <span class="nav-icon">📋</span>
          项目概览
        </button>
        <button
          :class="['nav-tab', { active: activeTab === 'chat' }]"
          @click="activeTab = 'chat'"
        >
          <span class="nav-icon">💬</span>
          检索会话
        </button>
      </nav>
      <div class="header-right">
        <span class="status-badge">
          <span class="status-dot"></span>
          服务运行中
        </span>
      </div>
    </header>

    <!-- 主内容区 -->
    <main class="app-main">
      <OverviewTab v-if="activeTab === 'overview'" />
      <ChatTab v-if="activeTab === 'chat'" />
    </main>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import OverviewTab from './components/OverviewTab.vue'
import ChatTab from './components/ChatTab.vue'

const activeTab = ref('overview')
</script>

<style scoped>
.app-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #f0f2f5;
}

/* 顶部导航 */
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 56px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
  position: relative;
  z-index: 10;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.logo {
  display: flex;
  align-items: center;
  gap: 8px;
}

.logo-icon {
  font-size: 24px;
}

.logo-text {
  font-size: 18px;
  font-weight: 700;
  color: #1a1a2e;
  letter-spacing: 0.5px;
}

/* 导航 Tab */
.header-nav {
  display: flex;
  gap: 4px;
}

.nav-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 20px;
  background: transparent;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  color: #606266;
  cursor: pointer;
  transition: all 0.2s;
}

.nav-tab:hover {
  background: #f5f7fa;
  color: #409eff;
}

.nav-tab.active {
  background: #ecf5ff;
  color: #409eff;
  font-weight: 600;
}

.nav-icon {
  font-size: 16px;
}

/* 右侧状态 */
.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #67c23a;
  padding: 4px 12px;
  background: #f0f9eb;
  border-radius: 12px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #67c23a;
  animation: blink 2s infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* 主内容 */
.app-main {
  flex: 1;
  overflow: hidden;
}
</style>
