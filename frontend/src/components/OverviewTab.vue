<template>
  <div class="overview-tab">
    <!-- 顶部 Hero -->
    <div class="hero-section">
      <div class="hero-icon">🏦</div>
      <h1>Finance Data Agent</h1>
      <p class="hero-subtitle">面向零售银行、消费信贷和财富管理场景的智能金融问数平台</p>
    </div>

    <!-- Tab 切换 -->
    <div class="inner-tabs">
      <button
        v-for="t in tabs"
        :key="t.key"
        :class="['inner-tab', { active: activeTab === t.key }]"
        @click="activeTab = t.key"
      >
        {{ t.icon }} {{ t.label }}
      </button>
    </div>

    <!-- 内容区 -->
    <div class="tab-content">
      <!-- 主线业务流程 -->
      <div v-if="activeTab === 'flow'" class="content-section">
        <h2 class="section-title">NL2SQL 处理流程</h2>
        <p class="section-desc">用户输入自然语言问题，Agent 自动完成查询理解、语义检索、SQL 生成与执行，最终返回结构化结果。</p>

        <div class="flow-container">
          <!-- 流程图 -->
          <div class="flow-diagram">
            <!-- 第1行：输入 + 分类 + 关键词 -->
            <div class="flow-row">
              <div class="flow-node" style="background: #e3f2fd; border-color: #2196f3;">
                <div class="node-icon">🗣️</div>
                <div class="node-title">自然语言输入</div>
                <div class="node-desc">用户提问</div>
              </div>
              <div class="flow-arrow">→</div>
              <div class="flow-node" style="background: #e8f5e9; border-color: #4caf50;">
                <div class="node-icon">🏷️</div>
                <div class="node-title">查询分类</div>
                <div class="node-desc">类型/领域/时间范围</div>
              </div>
              <div class="flow-arrow">→</div>
              <div class="flow-node" style="background: #fff3e0; border-color: #ff9800;">
                <div class="node-icon">🔑</div>
                <div class="node-title">抽取关键词</div>
                <div class="node-desc">同义词标准化 / jieba分词</div>
              </div>
            </div>
            <!-- 第2行：三路并行召回 -->
            <div class="flow-row">
              <div class="flow-node" style="background: #f3e5f5; border-color: #9c27b0;">
                <div class="node-icon">📐</div>
                <div class="node-title">召回字段信息</div>
                <div class="node-desc">Qdrant 向量检索</div>
              </div>
              <div class="flow-arrow">‖</div>
              <div class="flow-node" style="background: #f3e5f5; border-color: #9c27b0;">
                <div class="node-icon">📏</div>
                <div class="node-title">召回值信息</div>
                <div class="node-desc">ES 字段值检索</div>
              </div>
              <div class="flow-arrow">‖</div>
              <div class="flow-node" style="background: #f3e5f5; border-color: #9c27b0;">
                <div class="node-icon">📊</div>
                <div class="node-title">召回指标信息</div>
                <div class="node-desc">Qdrant 指标检索</div>
              </div>
            </div>
            <!-- 第3行：融合 + 过滤 -->
            <div class="flow-row">
              <div class="flow-node" style="background: #e0f7fa; border-color: #00bcd4;">
                <div class="node-icon">🔗</div>
                <div class="node-title">融合检索信息</div>
                <div class="node-desc">合并去重</div>
              </div>
              <div class="flow-arrow">→</div>
              <div class="flow-node" style="background: #e8eaf6; border-color: #3f51b5;">
                <div class="node-icon">🔍</div>
                <div class="node-title">过滤表/指标信息</div>
                <div class="node-desc">LLM 精准筛选</div>
              </div>
              <div class="flow-arrow">→</div>
              <div class="flow-node" style="background: #e8eaf6; border-color: #3f51b5;">
                <div class="node-icon">📚</div>
                <div class="node-title">补充上下文</div>
                <div class="node-desc">表结构 + 字段说明</div>
              </div>
            </div>
            <!-- 第4行：SQL 生成 -->
            <div class="flow-row">
              <div class="flow-node" style="background: #fff8e1; border-color: #ffc107;">
                <div class="node-icon">⚡</div>
                <div class="node-title">生成 SQL</div>
                <div class="node-desc">DeepSeek LLM</div>
              </div>
              <div class="flow-arrow">→</div>
              <div class="flow-node" style="background: #fce4ec; border-color: #e91e63;">
                <div class="node-icon">✅</div>
                <div class="node-title">验证 SQL</div>
                <div class="node-desc">语法/表名/字段校验</div>
              </div>
              <div class="flow-arrow">→</div>
              <div class="flow-node" style="background: #fbe9e7; border-color: #ff5722;">
                <div class="node-icon">🔄</div>
                <div class="node-title">校正 SQL</div>
                <div class="node-desc">错误时自动修正</div>
              </div>
              <div class="flow-arrow">→</div>
              <div class="flow-node" style="background: #e8f5e9; border-color: #4caf50;">
                <div class="node-icon">▶️</div>
                <div class="node-title">执行 SQL</div>
                <div class="node-desc">MySQL DW 库执行</div>
              </div>
            </div>
            <!-- 第5行：结果格式化 -->
            <div class="flow-row">
              <div class="flow-node" style="background: #e0f2f1; border-color: #009688;">
                <div class="node-icon">📝</div>
                <div class="node-title">生成结果说明</div>
                <div class="node-desc">自然语言总结</div>
              </div>
              <div class="flow-arrow">→</div>
              <div class="flow-node" style="background: #c8e6c9; border-color: #2e7d32;">
                <div class="node-icon">📋</div>
                <div class="node-title">返回结果</div>
                <div class="node-desc">结构化数据 + 表格</div>
              </div>
            </div>
          </div>

          <!-- 核心节点列表 -->
          <div class="capabilities-grid">
            <div class="capability-card" v-for="cap in nl2sqlNodes" :key="cap.title">
              <div class="cap-icon">{{ cap.icon }}</div>
              <div class="cap-title">{{ cap.title }}</div>
              <div class="cap-desc">{{ cap.desc }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 技术架构亮点 -->
      <div v-if="activeTab === 'arch'" class="content-section">
        <h2 class="section-title">技术架构亮点</h2>
        <p class="section-desc">基于 LangGraph Agent + 多存储引擎的 RAG 架构，实现从自然语言到结构化查询的端到端智能问数。</p>

        <div class="arch-container">
          <!-- 架构图 -->
          <div class="arch-diagram">
            <div class="arch-layer">
              <div class="layer-label">用户交互层</div>
              <div class="layer-nodes">
                <div class="arch-node">前端界面 (Vue3)</div>
                <div class="arch-node">RESTful API</div>
                <div class="arch-node">SSE 流式响应</div>
              </div>
            </div>
            <div class="arch-layer">
              <div class="layer-label">Agent 编排层 (LangGraph)</div>
              <div class="layer-nodes">
                <div class="arch-node small">Query 分类</div>
                <div class="arch-node small">关键词提取</div>
                <div class="arch-node small">指标/表/字段 召回</div>
                <div class="arch-node small">信息融合</div>
                <div class="arch-node small">SQL 生成</div>
                <div class="arch-node small">SQL 校验修正</div>
                <div class="arch-node small">结果格式化</div>
              </div>
            </div>
            <div class="arch-layer">
              <div class="layer-label">语义检索层 (Multi-Store RAG)</div>
              <div class="layer-nodes">
                <div class="arch-node">Qdrant 向量库 (指标/字段语义)</div>
                <div class="arch-node">Elasticsearch (字段值检索)</div>
                <div class="arch-node">TEI Embedding (bge-large-zh)</div>
              </div>
            </div>
            <div class="arch-layer">
              <div class="layer-label">数据存储层</div>
              <div class="layer-nodes">
                <div class="arch-node">MySQL (元数据 + 业务数据)</div>
                <div class="arch-node">LLM (DeepSeek Chat)</div>
              </div>
            </div>
          </div>

          <!-- 技术亮点卡片 -->
          <div class="highlights-grid">
            <div class="highlight-card" v-for="hl in highlights" :key="hl.title">
              <div class="hl-header">
                <span class="hl-icon">{{ hl.icon }}</span>
                <span class="hl-title">{{ hl.title }}</span>
              </div>
              <div class="hl-body">{{ hl.desc }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 未来技术展望 -->
      <div v-if="activeTab === 'future'" class="content-section">
        <h2 class="section-title">未来技术展望</h2>
        <p class="section-desc">持续演进，构建更加智能、高效、安全的金融业务数据分析平台。</p>

        <div class="future-container">
          <div class="timeline">
            <div class="timeline-item" v-for="(item, idx) in roadmap" :key="idx">
              <div class="timeline-dot" :style="{ background: item.color }"></div>
              <div class="timeline-content">
                <div class="timeline-phase">{{ item.phase }}</div>
                <div class="timeline-title">{{ item.title }}</div>
                <div class="timeline-desc">{{ item.desc }}</div>
                <div class="timeline-tags">
                  <span v-for="tag in item.tags" :key="tag" class="tag">{{ tag }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const activeTab = ref('flow')

const tabs = [
  { key: 'flow', label: '主线业务流程', icon: '🔄' },
  { key: 'arch', label: '技术架构亮点', icon: '🏗️' },
  { key: 'future', label: '未来技术展望', icon: '🚀' },
]

const nl2sqlNodes = [
  { icon: '🏷️', title: '查询分类', desc: '识别查询类型、业务领域、时间范围' },
  { icon: '🔑', title: '抽取关键词', desc: '同义词标准化、jieba 分词' },
  { icon: '📐', title: '召回字段信息', desc: 'Qdrant 向量检索 Top-K' },
  { icon: '📏', title: '召回值信息', desc: 'ES 字段值倒排检索' },
  { icon: '📊', title: '召回指标信息', desc: 'Qdrant 指标语义检索' },
  { icon: '🔗', title: '融合检索信息', desc: '三路结果合并去重' },
  { icon: '🔍', title: '过滤表/指标', desc: 'LLM 精准筛选匹配项' },
  { icon: '⚡', title: '生成 SQL', desc: 'DeepSeek LLM 生成' },
  { icon: '✅', title: '验证 SQL', desc: '语法、表名、字段校验' },
  { icon: '🔄', title: '校正 SQL', desc: '错误时自动修正重写' },
  { icon: '▶️', title: '执行 SQL', desc: 'MySQL DW 库执行查询' },
  { icon: '📝', title: '生成结果说明', desc: '自然语言总结返回' },
]

const highlights = [
  { icon: '🤖', title: 'LangGraph Agent 编排', desc: '基于 LangGraph 的有状态 Agent 框架，支持多步骤推理、循环修正和流式输出，实现复杂的 NL2SQL 任务编排。' },
  { icon: '🔍', title: 'Multi-Store RAG 检索', desc: '融合 Qdrant 向量检索、ES 关键词匹配、Embedding 语义理解，实现指标/表/字段/值的多维度精准召回。' },
  { icon: '🔄', title: 'SQL 自校验修正', desc: '生成 SQL 后自动执行校验，支持错误修正和重写循环，大幅提升 SQL 生成准确率和鲁棒性。' },
  { icon: '📡', title: 'SSE 流式交互', desc: '基于 Server-Sent Events 的流式响应，实时展示查询进度、执行步骤和中间结果，提升用户体验。' },
  { icon: '🧠', title: '语义理解增强', desc: 'DeepSeek Chat + bge-large-zh 深度语义理解，支持同义词识别、业务别名映射和自然语言意图解析。' },
  { icon: '🏗️', title: '分层解耦架构', desc: 'FastAPI + LangGraph + Repository 多层解耦，支持多存储引擎灵活替换和水平扩展。' },
]

const roadmap = [
  {
    phase: 'Phase 1',
    title: '对话式分析增强',
    desc: '支持多轮对话、上下文记忆、追问澄清，实现连续的业务分析对话能力。',
    tags: ['多轮对话', '上下文记忆', '追问澄清'],
    color: '#4caf50',
  },
  {
    phase: 'Phase 2',
    title: '智能报表与可视化',
    desc: '自动生成图表、趋势分析和对比报表，支持柱状图、折线图、饼图等多种可视化形式。',
    tags: ['ECharts', '自动图表', '趋势分析'],
    color: '#2196f3',
  },
  {
    phase: 'Phase 3',
    title: '多数据源联邦查询',
    desc: '接入更多数据源（API、文件、实时流），实现跨源联邦查询和统一数据视图。',
    tags: ['联邦查询', '多源融合', '实时数据'],
    color: '#ff9800',
  },
  {
    phase: 'Phase 4',
    title: '指标中台与自助分析',
    desc: '构建统一的指标管理平台，支持自定义指标配置、拖拽式分析和自助报表。',
    tags: ['指标管理', '自助分析', '低代码'],
    color: '#9c27b0',
  },
  {
    phase: 'Phase 5',
    title: '安全与权限体系',
    desc: '完善行级/列级权限控制、敏感数据脱敏、操作审计日志等企业级安全能力。',
    tags: ['权限控制', '数据脱敏', '审计日志'],
    color: '#e91e63',
  },
]
</script>

<style scoped>
.overview-tab {
  height: 100%;
  overflow-y: auto;
  padding: 0;
}

/* Hero */
.hero-section {
  text-align: center;
  padding: 40px 20px 30px;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
  color: #fff;
}

.hero-icon {
  font-size: 56px;
  margin-bottom: 12px;
}

.hero-section h1 {
  font-size: 32px;
  font-weight: 700;
  margin: 0 0 10px;
  background: linear-gradient(90deg, #66b1ff, #a8e6cf);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.hero-subtitle {
  font-size: 16px;
  color: rgba(255, 255, 255, 0.7);
  margin: 0;
}

/* Inner Tabs */
.inner-tabs {
  display: flex;
  justify-content: center;
  gap: 4px;
  padding: 0 20px;
  margin-top: -20px;
  position: relative;
  z-index: 2;
}

.inner-tab {
  padding: 10px 24px;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-bottom: none;
  border-radius: 10px 10px 0 0;
  font-size: 15px;
  font-weight: 500;
  color: #606266;
  cursor: pointer;
  transition: all 0.2s;
}

.inner-tab:hover {
  color: #409eff;
}

.inner-tab.active {
  background: #f0f2f5;
  color: #409eff;
  font-weight: 600;
  border-color: #409eff;
}

/* Content */
.tab-content {
  padding: 30px 40px 60px;
  background: #f0f2f5;
  min-height: calc(100vh - 200px);
}

.content-section {
  max-width: 1100px;
  margin: 0 auto;
}

.section-title {
  font-size: 24px;
  font-weight: 700;
  color: #1a1a2e;
  margin: 0 0 8px;
}

.section-desc {
  font-size: 14px;
  color: #909399;
  margin: 0 0 28px;
}

/* Flow Diagram */
.flow-container {
  display: flex;
  flex-direction: column;
  gap: 30px;
}

.flow-diagram {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 24px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.flow-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  flex-wrap: wrap;
}

.flow-node {
  min-width: 140px;
  max-width: 180px;
  padding: 14px 16px;
  border-radius: 10px;
  border: 2px solid;
  text-align: center;
  transition: transform 0.2s, box-shadow 0.2s;
}

.flow-node:hover {
  transform: translateY(-3px);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.1);
}

.node-icon {
  font-size: 28px;
  margin-bottom: 6px;
}

.node-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.node-desc {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.flow-arrow {
  font-size: 20px;
  color: #c0c4cc;
  font-weight: 700;
}

/* Capabilities */
.capabilities-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 14px;
}

.capability-card {
  background: #fff;
  border-radius: 10px;
  padding: 18px;
  text-align: center;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  transition: all 0.2s;
}

.capability-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
}

.cap-icon {
  font-size: 28px;
  margin-bottom: 8px;
}

.cap-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.cap-desc {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
  line-height: 1.5;
}

/* Architecture */
.arch-container {
  display: flex;
  flex-direction: column;
  gap: 30px;
}

.arch-diagram {
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.arch-layer {
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px dashed #e4e7ed;
}

.arch-layer:last-child {
  margin-bottom: 0;
  padding-bottom: 0;
  border-bottom: none;
}

.layer-label {
  font-size: 13px;
  font-weight: 600;
  color: #409eff;
  margin-bottom: 10px;
  padding: 4px 12px;
  background: #ecf5ff;
  border-radius: 4px;
  display: inline-block;
}

.layer-nodes {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.arch-node {
  padding: 10px 18px;
  background: #f5f7fa;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  font-size: 14px;
  color: #606266;
  transition: all 0.2s;
}

.arch-node:hover {
  border-color: #409eff;
  color: #409eff;
  background: #ecf5ff;
}

.arch-node.small {
  font-size: 13px;
  padding: 8px 14px;
}

/* Highlights */
.highlights-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
}

.highlight-card {
  background: #fff;
  border-radius: 10px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  transition: all 0.2s;
}

.highlight-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.08);
}

.hl-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.hl-icon {
  font-size: 22px;
}

.hl-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.hl-body {
  font-size: 13px;
  color: #606266;
  line-height: 1.7;
}

/* Future Roadmap */
.future-container {
  max-width: 800px;
  margin: 0 auto;
}

.timeline {
  position: relative;
  padding-left: 30px;
}

.timeline::before {
  content: '';
  position: absolute;
  left: 11px;
  top: 8px;
  bottom: 8px;
  width: 2px;
  background: #e4e7ed;
}

.timeline-item {
  position: relative;
  margin-bottom: 28px;
}

.timeline-item:last-child {
  margin-bottom: 0;
}

.timeline-dot {
  position: absolute;
  left: -25px;
  top: 6px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 3px solid #fff;
  box-shadow: 0 0 0 2px currentColor;
}

.timeline-content {
  background: #fff;
  border-radius: 10px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.timeline-phase {
  font-size: 12px;
  font-weight: 600;
  color: #409eff;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.timeline-title {
  font-size: 18px;
  font-weight: 700;
  color: #303133;
  margin: 4px 0 8px;
}

.timeline-desc {
  font-size: 14px;
  color: #606266;
  line-height: 1.6;
  margin-bottom: 10px;
}

.timeline-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.tag {
  font-size: 12px;
  padding: 3px 10px;
  background: #ecf5ff;
  color: #409eff;
  border-radius: 12px;
}
</style>
