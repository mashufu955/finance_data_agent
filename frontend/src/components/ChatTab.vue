<template>
  <div class="chat-page">
    <div class="chat-layout">
      <!-- 左侧：历史会话 -->
      <div class="sidebar">
        <div class="sidebar-header">
          <span class="sidebar-title">历史会话</span>
          <button class="new-chat-btn" @click="startNewChat" title="新建会话">
            ＋ 新会话
          </button>
        </div>
        <div class="session-list">
          <div
            v-for="session in sessions"
            :key="session.id"
            :class="['session-item', { active: currentSessionId === session.id }]"
            @click="switchSession(session.id)"
          >
            <div class="session-icon">💬</div>
            <div class="session-info">
              <div class="session-title">{{ session.title }}</div>
              <div class="session-time">{{ session.time }}</div>
            </div>
            <button class="delete-btn" @click.stop="deleteSession(session.id)" title="删除">✕</button>
          </div>
          <div v-if="sessions.length === 0" class="empty-sessions">
            暂无历史会话
          </div>
        </div>
      </div>

      <!-- 右侧：聊天区 -->
      <div class="chat-main">
        <!-- 消息区 -->
        <div ref="messagesEl" class="messages">
          <!-- 欢迎消息 -->
          <div v-if="messages.length === 0" class="welcome">
            <div class="welcome-icon">🏦</div>
            <div class="welcome-title">金融智能问数平台</div>
            <div class="welcome-desc">通过自然语言查询金融业务数据，支持客户、账户、交易、理财、信贷、还款、风控、催收等多维度分析</div>
            <div class="example-list">
              <div class="example-title">试试这些问题：</div>
              <div class="example-item" v-for="ex in examples" :key="ex" @click="sendExample(ex)">
                {{ ex }}
              </div>
            </div>
          </div>

          <div
            v-for="(msg, index) in messages"
            :key="index"
            :class="['message-row', msg.role]"
          >
            <div v-if="msg.role === 'assistant'" class="avatar">🤖</div>

            <div class="bubble">
              <!-- 文本消息 -->
              <div v-if="msg.type === 'text'" class="text-content">{{ msg.content }}</div>

              <!-- 步骤 -->
              <div v-else-if="msg.type === 'steps'" class="steps">
                <div v-for="(step, sIdx) in msg.steps" :key="sIdx" class="step">
                  <span class="dot" :class="step.status"></span>
                  <span>{{ step.text }}</span>
                </div>
              </div>

              <!-- 表格 -->
              <div v-else-if="msg.type === 'table'" class="table-wrap">
                <table class="result-table">
                  <thead>
                    <tr>
                      <th v-for="col in msg.columns" :key="col">{{ col }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(row, rIdx) in msg.rows" :key="rIdx">
                      <td v-for="col in msg.columns" :key="col">{{ row[col] }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <!-- 错误 -->
              <div v-else-if="msg.type === 'error'" class="error-text">
                {{ msg.content }}
              </div>

              <!-- SQL -->
              <div v-else-if="msg.type === 'sql'" class="sql-block">
                <div class="sql-header">
                  <span>🔍 生成的 SQL</span>
                </div>
                <pre><code>{{ msg.content }}</code></pre>
              </div>
            </div>

            <div v-if="msg.role === 'user'" class="avatar">🧑</div>
          </div>
          <div class="messages-bottom-spacer"></div>
        </div>

        <!-- 输入区 -->
        <div class="input-wrapper">
          <div class="input-box">
            <div class="input-row">
              <input
                v-model="question"
                @keyup.enter="sendQuestion"
                placeholder="请输入你的问题，例如：本月新增客户数是多少？"
                :disabled="loading"
              />
              <button @click="sendQuestion" :disabled="loading || !question.trim()">
                {{ loading ? '执行中...' : '发送' }}
              </button>
            </div>
          </div>
          <div class="input-hint">
            支持自然语言查询 · 结果仅供参考 · 按机构/渠道/时间等维度可拆分分析
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { nextTick, ref, onMounted } from 'vue'

const API_URL = '/api/query'

const question = ref('')
const loading = ref(false)
const messages = ref([])
const messagesEl = ref(null)
const sessions = ref([])
const currentSessionId = ref(null)
const chatHistory = ref({})

const examples = [
  '本月新增客户数是多少？',
  '当前正常账户数是多少？',
  '最近30天交易金额和交易笔数是多少？',
  '不同风险等级的客户分布如何？',
  '当前理财持仓规模是多少？',
  '本月贷款申请数和放款金额是多少？',
]

function scrollToBottom() {
  const el = messagesEl.value
  if (!el) return
  el.scrollTop = el.scrollHeight
}

function generateSessionId() {
  return 'session_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8)
}

function formatTime() {
  const now = new Date()
  const h = String(now.getHours()).padStart(2, '0')
  const m = String(now.getMinutes()).padStart(2, '0')
  return `${h}:${m}`
}

function saveSessions() {
  try {
    localStorage.setItem('fda_sessions', JSON.stringify(sessions.value))
    localStorage.setItem('fda_history', JSON.stringify(chatHistory.value))
  } catch (e) {
    // ignore
  }
}

function loadSessions() {
  try {
    const saved = localStorage.getItem('fda_sessions')
    const history = localStorage.getItem('fda_history')
    if (saved) sessions.value = JSON.parse(saved)
    if (history) chatHistory.value = JSON.parse(history)
  } catch (e) {
    // ignore
  }
}

onMounted(() => {
  loadSessions()
  if (sessions.value.length === 0) {
    startNewChat()
  } else {
    const lastSession = sessions.value[sessions.value.length - 1]
    switchSession(lastSession.id)
  }
})

function startNewChat() {
  const id = generateSessionId()
  const session = {
    id,
    title: '新会话',
    time: formatTime(),
    messageCount: 0,
  }
  sessions.value.push(session)
  chatHistory.value[id] = []
  currentSessionId.value = id
  messages.value = []
  saveSessions()
}

function switchSession(id) {
  currentSessionId.value = id
  messages.value = chatHistory.value[id] || []
  nextTick(() => scrollToBottom())
}

function deleteSession(id) {
  sessions.value = sessions.value.filter(s => s.id !== id)
  delete chatHistory.value[id]
  if (currentSessionId.value === id) {
    if (sessions.value.length > 0) {
      switchSession(sessions.value[sessions.value.length - 1].id)
    } else {
      startNewChat()
    }
  }
  saveSessions()
}

function sendExample(text) {
  question.value = text
  sendQuestion()
}

async function sendQuestion() {
  if (!question.value.trim() || loading.value) return

  const q = question.value.trim()
  question.value = ''
  loading.value = true

  messages.value.push({ role: 'user', type: 'text', content: q })

  const stepIndex = messages.value.push({
    role: 'assistant',
    type: 'steps',
    steps: [],
  }) - 1

  // Update session title if first message
  if (currentSessionId.value && messages.value.filter(m => m.role === 'user').length === 1) {
    const session = sessions.value.find(s => s.id === currentSessionId.value)
    if (session) {
      session.title = q.length > 20 ? q.slice(0, 20) + '...' : q
      saveSessions()
    }
  }

  await nextTick()
  scrollToBottom()

  try {
    const response = await fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: q }),
    })

    if (!response.body) throw new Error('服务器未返回流')

    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    while (true) {
      const { value, done } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const events = buffer.split('\n\n')
      buffer = events.pop()

      for (const evt of events) {
        const line = evt.trim()
        if (!line.startsWith('data:')) continue

        let data
        try {
          data = JSON.parse(line.replace(/^data:\s*/, ''))
        } catch {
          continue
        }

        const steps = messages.value[stepIndex].steps

        if (data.stage) {
          const last = steps.at(-1)
          if (last && last.status === 'running') last.status = 'success'
          steps.push({ text: data.stage, status: 'running' })
        }
        if (data.summary) {
          const last = steps.at(-1)
          if (last) last.status = 'success'
          messages.value.push({
            role: 'assistant',
            type: 'text',
            content: data.summary,
          })
        }
        if (data.error) {
          const last = steps.at(-1)
          if (last) last.status = 'error'
          messages.value.push({
            role: 'assistant',
            type: 'error',
            content: data.error,
          })
        }
        if (data.sql) {
          const last = steps.at(-1)
          if (last) last.status = 'success'
          messages.value.push({
            role: 'assistant',
            type: 'sql',
            content: data.sql,
          })
        }
        if (Array.isArray(data.result)) {
          const last = steps.at(-1)
          if (last) last.status = 'success'
          messages.value.push({
            role: 'assistant',
            type: 'table',
            columns: Object.keys(data.result[0] || {}),
            rows: data.result,
          })
        }

        await nextTick()
        scrollToBottom()
      }
    }
  } catch (e) {
    messages.value.push({
      role: 'assistant',
      type: 'error',
      content: e?.message || '请求失败',
    })
  } finally {
    loading.value = false
    // Save messages to session
    if (currentSessionId.value) {
      chatHistory.value[currentSessionId.value] = [...messages.value]
      const session = sessions.value.find(s => s.id === currentSessionId.value)
      if (session) {
        session.messageCount = messages.value.length
        session.time = formatTime()
      }
      saveSessions()
    }
    await nextTick()
    scrollToBottom()
  }
}
</script>

<style scoped>
.chat-page {
  height: 100%;
  overflow: hidden;
}

.chat-layout {
  display: flex;
  height: 100%;
}

/* 侧边栏 */
.sidebar {
  width: 240px;
  min-width: 240px;
  background: #fff;
  border-right: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
}

.sidebar-header {
  padding: 16px;
  border-bottom: 1px solid #e4e7ed;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sidebar-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.new-chat-btn {
  font-size: 12px;
  padding: 4px 10px;
  background: #ecf5ff;
  color: #409eff;
  border: 1px solid #b3d8ff;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.new-chat-btn:hover {
  background: #409eff;
  color: #fff;
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.session-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: 2px;
}

.session-item:hover {
  background: #f5f7fa;
}

.session-item.active {
  background: #ecf5ff;
  border: 1px solid #b3d8ff;
}

.session-icon {
  font-size: 16px;
}

.session-info {
  flex: 1;
  min-width: 0;
}

.session-title {
  font-size: 13px;
  color: #303133;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-time {
  font-size: 11px;
  color: #c0c4cc;
  margin-top: 2px;
}

.delete-btn {
  font-size: 12px;
  padding: 2px 6px;
  background: transparent;
  color: #c0c4cc;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  opacity: 0;
  transition: all 0.2s;
}

.session-item:hover .delete-btn {
  opacity: 1;
}

.delete-btn:hover {
  background: #fde2e2;
  color: #f56c6c;
}

.empty-sessions {
  text-align: center;
  padding: 40px 20px;
  color: #c0c4cc;
  font-size: 13px;
}

/* 聊天主区 */
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #fafbfc;
}

/* 消息区 */
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px 40px 20px;
}

/* 欢迎消息 */
.welcome {
  text-align: center;
  padding: 60px 20px 40px;
}

.welcome-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.welcome-title {
  font-size: 22px;
  font-weight: 700;
  color: #303133;
  margin-bottom: 8px;
}

.welcome-desc {
  font-size: 14px;
  color: #909399;
  max-width: 500px;
  margin: 0 auto 24px;
  line-height: 1.6;
}

.example-list {
  max-width: 500px;
  margin: 0 auto;
}

.example-title {
  font-size: 13px;
  color: #909399;
  margin-bottom: 10px;
}

.example-item {
  display: inline-block;
  padding: 6px 14px;
  margin: 4px;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 16px;
  font-size: 13px;
  color: #606266;
  cursor: pointer;
  transition: all 0.2s;
}

.example-item:hover {
  border-color: #409eff;
  color: #409eff;
  background: #ecf5ff;
}

/* 消息行 */
.message-row {
  display: flex;
  margin-bottom: 16px;
  align-items: flex-start;
}

.message-row.assistant {
  justify-content: flex-start;
}

.message-row.user {
  justify-content: flex-end;
}

.avatar {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: #f3f4f6;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  margin: 0 10px;
  flex-shrink: 0;
}

.bubble {
  max-width: min(820px, 75%);
  padding: 14px 18px;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

.message-row.user .bubble {
  background: #e6f4ff;
}

/* 文本 */
.text-content {
  font-size: 14px;
  line-height: 1.6;
  color: #303133;
  white-space: pre-wrap;
}

/* 步骤 */
.steps {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #606266;
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dot.running {
  background: #f1c40f;
  animation: pulse 1.5s infinite;
}

.dot.success {
  background: #2ecc71;
}

.dot.error {
  background: #e74c3c;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* 表格 */
.table-wrap {
  max-width: 100%;
  overflow-x: auto;
}

.result-table {
  width: max-content;
  min-width: 100%;
  table-layout: auto;
  border-collapse: collapse;
  font-size: 13px;
}

.result-table th,
.result-table td {
  border: 1px solid #e4e7ed;
  padding: 8px 14px;
  white-space: nowrap;
  text-align: left;
}

.result-table th {
  background: #f5f7fa;
  font-weight: 600;
  color: #303133;
  position: sticky;
  top: 0;
  z-index: 1;
}

.result-table td {
  color: #606266;
}

/* 错误 */
.error-text {
  color: #e74c3c;
  font-weight: 600;
  font-size: 14px;
}

/* SQL 块 */
.sql-block {
  background: #1e1e2e;
  border-radius: 8px;
  overflow: hidden;
}

.sql-header {
  padding: 8px 14px;
  background: #2d2d3a;
  font-size: 12px;
  color: #a8e6cf;
}

.sql-block pre {
  margin: 0;
  padding: 12px 14px;
  overflow-x: auto;
}

.sql-block code {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 12px;
  color: #e0e0e0;
  line-height: 1.6;
}

/* 输入区 */
.input-wrapper {
  padding: 16px 40px 20px;
  background: #fafbfc;
}

.input-box {
  background: #fff;
  border-radius: 12px;
  border: 1px solid #e4e7ed;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  overflow: hidden;
}

.input-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
}

.input-row input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  font-size: 14px;
  color: #303133;
}

.input-row input::placeholder {
  color: #c0c4cc;
}

.input-row button {
  padding: 8px 20px;
  border-radius: 8px;
  border: none;
  background: linear-gradient(135deg, #409eff, #66b1ff);
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.input-row button:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.3);
}

.input-row button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.input-hint {
  text-align: center;
  font-size: 12px;
  color: #c0c4cc;
  margin-top: 8px;
}

.messages-bottom-spacer {
  height: 20px;
}
</style>
