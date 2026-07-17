# Finance Data Agent Frontend

金融智能问数平台前端界面，基于 Vue 3 + Vite 构建。

## 功能

### Tab1 - 项目概览
- **主线业务流程**：展示从客户开户到贷后管理的完整金融生命周期
- **技术架构亮点**：LangGraph Agent + Multi-Store RAG 架构详解
- **未来技术展望**：平台演进路线图

### Tab2 - 检索会话
- 自然语言查询金融业务数据
- SSE 流式响应，实时展示执行步骤
- 支持表格结果展示和 SQL 展示
- 历史会话管理（localStorage 持久化）

## 快速开始

```bash
# 安装依赖
npm install

# 启动开发服务器（需要后端服务运行在 8000 端口）
npm run dev

# 构建生产版本
npm run build
```

## 后端依赖

确保后端服务已启动：
```bash
cd ..
python main.py
```

后端服务运行在 `http://127.0.0.1:8000`，前端通过 Vite 代理转发 `/api` 请求。

## 技术栈
- Vue 3 (Composition API + `<script setup>`)
- Vite 7
- 原生 CSS（无 UI 框架依赖）
