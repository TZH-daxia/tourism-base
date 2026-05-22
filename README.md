# Tourism Base
基于 `FastAPI + LangGraph + Vue 3 + Pinia + Vite` 的旅游知识库问答系统。

当前版本聚焦两个方向：
- 旅游资料导入、结构化、向量化与两段式 RAG 检索
- 可直接使用的前端产品层，包括广告首页、登录 demo、聊天页、知识库后台管理和运行时模型切换

## 当前能力

### 旅游知识库导入
- 支持 `PDF` 和 `Markdown`
- 按旅游语义提取 `城市 / 文档类型 / 产品名`
- 生成 `product_id`，用于把“实体集合”和“chunks 集合”关联起来
- 写入 Milvus 双集合
  - `ly_tourism_entities`：城市/产品/类型等实体检索入口
  - `ly_chunks`：正文切片、图片、来源等内容集合
- 同步写入 MongoDB 任务记录
- 支持 MinIO 图片对象访问

### 两段式 RAG 检索
- 第一步：先检索实体集合，确认城市/产品范围
- 第二步：再按 `product_id` 检索 chunks 集合
- 最终按旅游场景聚合 `交通 / 景点 / 酒店 / 美食 / 线路`
- 支持本地重排序模型适配
- 支持关闭知识库检索，直接走普通 AI 问答

### 前端产品体验
- 广告首页 + 登录 demo
- 聊天页支持推荐问法、消息复制、思考中状态、图片卡片展示
- 左下角设置菜单支持
  - 知识库后台管理入口
  - 模型切换弹窗
  - 退出登录回广告页
- 知识库后台支持
  - 上传文件
  - 查看任务
  - 进度轮询
  - 删除任务

## 项目结构

```text
tourism_base/
├─ main.py
├─ api/
│  └─ knowledge.py                 # 上传、任务、聊天、推荐、运行时模型设置
├─ core/
│  ├─ config.py                    # 全局配置 + 运行时模型覆盖
│  ├─ llm_factory.py               # LLM 工厂与缓存
│  ├─ milvus_manager.py            # Milvus 双集合管理
│  ├─ mongo_manager.py             # 会话历史、导入任务、推荐城市
│  ├─ minio_manager.py             # 图片与对象存储
│  └─ tourism_metadata.py          # 城市/文档类型/product_id 规则
├─ graphs/
│  ├─ graph_builder.py             # 导入图 + 查询图
│  └─ states.py                    # IngestState / RAGChatState
├─ nodes/
│  ├─ ingest/                      # 导入流程节点
│  └─ query/                       # 查询流程节点
├─ models/
│  └─ knowledge.py                 # Pydantic 请求/响应模型
├─ test/
│  ├─ test_api.py
│  └─ manual_tourism_dataset_flow.py
├─ web/
│  ├─ public/
│  │  └─ favicon.svg
│  ├─ src/
│  │  ├─ api/
│  │  │  └─ knowledge.ts
│  │  ├─ stores/
│  │  │  └─ chat.ts
│  │  ├─ components/
│  │  │  ├─ landing/
│  │  │  │  ├─ LandingPortal.vue
│  │  │  │  └─ LoginDemoModal.vue
│  │  │  ├─ chat/
│  │  │  │  └─ ChatView.vue
│  │  │  └─ knowledge/
│  │  │     └─ KnowledgeUpload.vue
│  │  ├─ App.vue
│  │  └─ main.ts
│  ├─ package.json
│  └─ index.html
├─ uploads/                        # 运行期上传目录
├─ test_output/                    # 测试报告输出
├─ pyproject.toml
└─ README.md
```

### 这次结构整理的重点
- 前端组件不再全部堆在 `web/src/components/`
- 按职责拆成 `landing / chat / knowledge`
- 首页入口、聊天主界面、知识库后台更容易定位

## 核心数据设计

### Milvus

#### `ly_tourism_entities`
用于第一段检索，先定位“城市 / 产品 / 可用资料类型”。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | `VARCHAR(64)` | 主键 |
| `task_id` | `VARCHAR(64)` | 导入任务 id |
| `product_id` | `VARCHAR(128)` | 产品主键，和 chunks 集合关联的核心字段 |
| `product_name` | `VARCHAR(128)` | 产品名，通常和城市名对齐 |
| `city` | `VARCHAR(64)` | 城市名 |
| `doc_type` | `VARCHAR(64)` | 文档类型，如交通/景点/酒店/美食/线路 |
| `aliases` | `VARCHAR(1024)` | 产品/城市别名 |
| `available_doc_types` | `VARCHAR(1024)` | 当前产品已入库的资料类型列表 |
| `suggested_queries` | `VARCHAR(2048)` | 推荐问法 |
| `source_file` | `VARCHAR(256)` | 来源文件名 |
| `dense_vector` | `FLOAT_VECTOR(1024)` | 稠密向量 |
| `sparse_vector` | `SPARSE_FLOAT_VECTOR` | 稀疏向量 |

说明：
- 查询流程先命中这个集合，拿到 `product_id`
- 再用 `product_id` 去过滤第二段 chunks 检索
- 这是保证“先查产品 / 城市，再查正文切片”的核心设计

#### `ly_chunks`
用于第二段检索，保存正文切片、来源和图片资源。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | `VARCHAR(64)` | 主键 |
| `task_id` | `VARCHAR(64)` | 导入任务 id |
| `product_id` | `VARCHAR(128)` | 和 `ly_tourism_entities.product_id` 对应 |
| `product_name` | `VARCHAR(128)` | 产品名 |
| `city` | `VARCHAR(64)` | 城市名 |
| `doc_type` | `VARCHAR(64)` | 文档类型 |
| `chunk_id` | `VARCHAR(160)` | 切片 id |
| `title` | `VARCHAR(256)` | 切片标题 |
| `content` | `VARCHAR(12000)` | 切片正文 |
| `source_file` | `VARCHAR(256)` | 来源文件名 |
| `source_url` | `VARCHAR(1024)` | 来源路径 / 外部地址 |
| `chunk_index` | `INT64` | 切片顺序 |
| `image_urls` | `VARCHAR(4096)` | 关联图片地址列表 |
| `image_alts` | `VARCHAR(4096)` | 图片说明列表 |
| `dense_vector` | `FLOAT_VECTOR(1024)` | 稠密向量 |
| `sparse_vector` | `SPARSE_FLOAT_VECTOR` | 稀疏向量 |

说明：
- 第二段检索主要从这个集合取正文
- `image_urls` / `image_alts` 会进入前端图片卡片展示
- `source_file` 用于知识库删除时回收 Milvus 数据

#### Milvus 设计重点
- `product_id` 是两个集合之间的主关联键
- `dense_vector + sparse_vector` 同时存在，支持 hybrid search
- `source_file` 是知识库后台删除时的清理依据
- `city / doc_type / product_name` 是后续 filter 和结果组织的重要维度

### MongoDB

#### `chat_messages`
一条 `session_id` 对应一份会话文档，内部用 `messages[]` 保存整段对话。

顶层字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `session_id` | `string` | 会话主键 |
| `title` | `string` | 会话标题 |
| `messages` | `array` | 全部消息 |
| `created_at` | `datetime` | 创建时间 |
| `updated_at` | `datetime` | 最后更新时间 |
| `migrated_to_session_document` | `bool` | 兼容老数据迁移标记 |

`messages[]` 子字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `message_id` | `string` | 消息 id |
| `role` | `string` | `user` / `assistant` |
| `content` | `string` | 消息文本 |
| `feedback` | `string` | 用户反馈 |
| `sources` | `array` | 来源列表 |
| `images` | `array` | 图片列表 |
| `timestamp` | `datetime` | 消息时间 |
| `intent` | `string` | 意图，可选 |
| `entities` | `object` | 实体，可选 |
| `rewritten_query` | `string` | 重写问题，可选 |

#### `import_tasks`
保存导入任务、阶段、进度、错误、推荐城市和文档元信息。

| 字段 | 类型 | 说明 |
|---|---|---|
| `task_id` | `string` | 任务主键 |
| `file_name` | `string` | 上传文件名 |
| `city` | `string` | 从文件名推断出的城市 |
| `doc_type` | `string` | 文件类型 |
| `product_id` | `string` | 和 Milvus 双集合关联的主键 |
| `status` | `string` | `processing / completed / failed` |
| `progress` | `float` | 进度值 |
| `current_step` | `string` | 当前阶段 |
| `stats` | `object` | 导入统计，如 `chunks/images/city/doc_type` |
| `error_log` | `array` | 错误日志 |
| `suggested_queries` | `array` | 推荐问法 |
| `timeline` | `array` | 分阶段进度轨迹 |
| `created_at` | `datetime` | 创建时间 |
| `updated_at` | `datetime` | 更新时间 |

`timeline[]` 子字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `step` | `string` | 阶段名 |
| `progress` | `float` | 阶段进度 |
| `status` | `string` | 阶段状态 |
| `detail` | `string` | 详细说明 |
| `timestamp` | `datetime` | 更新时间 |

#### MongoDB 设计重点
- `chat_messages` 采用单会话单文档模型，前端历史恢复更简单
- `import_tasks.product_id` 和 Milvus 设计一致，方便后台联查
- `timeline` 驱动知识库后台的阶段展示
- 推荐城市和推荐问法来自 `completed` 任务聚合

### MinIO

虽然当前没有单独落表，但对象命名规则和代理地址是固定设计的一部分。

#### 对象命名

对象名由下面的结构拼接：

```text
tourism/{city}/{doc_type}/{task_id}/{file_name}
```

对应代码规则：
- `city`：城市名，默认 `unknown`
- `doc_type`：资料类型，默认 `misc`
- `task_id`：导入任务 id
- `file_name`：原始文件名

#### MinIO 相关字段/概念

| 字段 / 概念 | 说明 |
|---|---|
| `bucket_name` | 当前桶名，来自环境变量 |
| `object_name` | MinIO 内部对象路径 |
| `content_type` | 对象媒体类型 |
| `source_url` | 在 chunk 中保留的来源地址 |
| `image_urls` | chunk 中保存的图片代理地址列表 |
| `image_alts` | chunk 中保存的图片说明列表 |

#### 前端访问方式

图片不会直接暴露 MinIO 地址，而是通过代理接口访问：

```text
/api/knowledge/assets/{bucket_name}/{object_path}
```

#### MinIO 设计重点
- 图片、解析结果和原始资源都可以按统一对象名组织
- `build_proxy_url()` 负责把对象名转成前端可访问地址
- 前端图片问答依赖 `image_urls + image_alts`

## 运行方式

### 后端

```powershell
uv sync
uv run python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

接口文档：
- [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### 前端

```powershell
cd web
npm install
npm run dev
```

开发地址：
- [http://127.0.0.1:5173](http://127.0.0.1:5173)

生产构建：

```powershell
cd web
npm run build
```

## 关键接口

### 知识库后台
- `POST /api/knowledge/upload`
- `GET /api/knowledge/status/{task_id}`
- `GET /api/knowledge/tasks`
- `DELETE /api/knowledge/task/{task_id}`
- `GET /api/knowledge/recommendations`

### 聊天
- `POST /api/knowledge/chat/stream`
- `POST /api/knowledge/chat`
- `GET /api/knowledge/chat/{session_id}/history`
- `DELETE /api/knowledge/chat/{session_id}`

### 运行时模型切换
- `GET /api/knowledge/runtime-model-settings`
- `POST /api/knowledge/runtime-model-settings`

### 资源代理
- `GET /api/knowledge/assets/{bucket_name}/{object_path}`

## 接口文档补充

### 1. 上传接口

#### `POST /api/knowledge/upload`

请求方式：
- `multipart/form-data`

请求字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `file` | `UploadFile` | 上传的 PDF 或 Markdown 文件 |

响应示例：

```json
{
  "task_id": "a1b2c3d4e5f6g7h8",
  "file_name": "三亚景点攻略.md",
  "status": "processing",
  "message": "文件已上传"
}
```

### 2. 任务状态接口

#### `GET /api/knowledge/status/{task_id}`

响应字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `task_id` | `string` | 任务 id |
| `file_name` | `string` | 文件名 |
| `status` | `string` | `processing / completed / failed` |
| `progress` | `number` | 进度 |
| `current_step` | `string` | 当前阶段 |
| `error` | `string` | 错误信息 |
| `city` | `string` | 城市 |
| `doc_type` | `string` | 文档类型 |
| `product_id` | `string` | 产品主键 |
| `suggested_queries` | `string[]` | 推荐问法 |
| `timeline` | `TaskTimelineItem[]` | 阶段轨迹 |
| `stats` | `object` | 统计信息 |

### 3. 推荐城市接口

#### `GET /api/knowledge/recommendations`

响应示例：

```json
[
  {
    "city": "杭州",
    "product_id": "hangzhou",
    "doc_types": ["交通指南", "景点攻略", "酒店信息"],
    "queries": ["杭州有什么好玩的？", "杭州住哪里方便？"]
  }
]
```

### 4. 运行时模型切换接口

#### `GET /api/knowledge/runtime-model-settings`

#### `POST /api/knowledge/runtime-model-settings`

请求体：

```json
{
  "api_key": "sk-xxx",
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-4.1-mini"
}
```

响应字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `api_key` | `string` | 当前运行时 API Key |
| `base_url` | `string` | 当前运行时 Base URL |
| `model` | `string` | 当前运行时模型名 |
| `vision_required` | `boolean` | 是否建议视觉模型 |
| `warning` | `string` | 提示文案 |

### 5. 非流式聊天接口

#### `POST /api/knowledge/chat`

请求体：

```json
{
  "message": "三亚有什么好玩的？",
  "session_id": "session_xxx",
  "rag_enabled": true
}
```

响应字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `session_id` | `string` | 会话 id |
| `message` | `string` | 回复文本 |
| `sources` | `array` | 命中的来源列表 |
| `citations` | `array` | 引用列表 |
| `images` | `array` | 图片列表 |
| `timestamp` | `datetime` | 回复时间 |

### 6. 流式聊天接口

#### `POST /api/knowledge/chat/stream`

请求体同非流式接口，响应方式为 `SSE`。

前端解析的事件类型：

| 类型 | 说明 |
|---|---|
| `token` | 增量文本 |
| `done` | 流结束 |
| `error` | 错误事件 |

典型 SSE 数据格式：

```text
data: {"token":"三亚","session_id":"xxx"}
data: {"token":"有很多值得去的地方","session_id":"xxx"}
data: {"done":true,"session_id":"xxx","sources":[...],"images":[...],"rag_referenced":true}
```

### 7. 历史会话接口

#### `GET /api/knowledge/chat/{session_id}/history`

响应示例：

```json
{
  "session_id": "session_xxx",
  "messages": [
    {
      "role": "user",
      "content": "三亚有什么好玩的？",
      "timestamp": "2026-05-22T12:00:00Z",
      "images": [],
      "sources": []
    }
  ],
  "total": 2
}
```

## 数据传输方式

### 1. 前端到后端

#### 文件上传
- 使用 `FormData`
- 入口：`knowledgeApi.upload(file)`
- 对应接口：`POST /api/knowledge/upload`

#### 普通接口
- 使用 `application/json`
- 适用于：
  - 模型切换
  - 非流式聊天
  - 删除会话
  - 删除任务

### 2. 后端到前端

#### JSON 响应
- 任务列表
- 历史消息
- 推荐城市
- 运行时模型设置

#### SSE 流式响应
- 聊天增量 token
- 完成态 `done`
- 错误态 `error`

### 3. 图片与资源传输

#### MinIO 对象 -> 代理接口 -> 前端

流程：

```text
MinIO object_name
→ build_proxy_url()
→ /api/knowledge/assets/{bucket}/{object_path}
→ 前端 image_urls
→ 聊天图片卡片展示
```

### 4. 前端内部数据契约

`web/src/api/knowledge.ts` 中的主要类型：

| 类型 | 说明 |
|---|---|
| `TaskStatus` | 知识库任务状态 |
| `RecommendationCard` | 推荐城市卡片 |
| `RuntimeModelSettings` | 运行时模型配置 |
| `ChatImage` | 聊天图片项 |
| `ChatSource` | 聊天来源项 |
| `ChatMessage` | 聊天消息 |
| `StreamChunk` | SSE 流片段 |

## 前端设计说明

### 页面分层

#### `landing/`
- `LandingPortal.vue`
  - 广告首页
  - 国际化展示
  - 粒子场与轻失重效果
  - 统一承接登录入口
- `LoginDemoModal.vue`
  - 登录 demo 弹窗
  - 不校验账号密码

#### `chat/`
- `ChatView.vue`
  - 推荐问法
  - 会话列表
  - 聊天消息
  - 设置菜单
  - 模型切换弹窗
  - 知识库检索开关

#### `knowledge/`
- `KnowledgeUpload.vue`
  - 知识库后台管理
  - 上传、轮询、过滤、删除
  - 全流程阶段展示

### 设计原则
- 首页采用国际化白色主体风格
- 聊天页强调旅游产品感，而不是纯后台感
- 知识库区域按“后台管理台”设计，不只是上传按钮
- 检索开关、模型切换、知识库后台统一走清晰的控制面板逻辑

## 环境变量

以下是最常用的配置项：

```env
OPENAI_API_KEY=your_api_key
OPENAI_API_BASE=https://api.siliconflow.cn/v1
LLM_DEFAULT_MODEL=Pro/moonshotai/Kimi-K2.5

MONGO_URL=mongodb://127.0.0.1:27017
MONGO_DB_NAME=tourism_kb

MILVUS_URL=http://127.0.0.1:19530
CHUNKS_COLLECTION=ly_chunks
ENTITIES_COLLECTION=ly_tourism_entities

MINIO_ENDPOINT=127.0.0.1:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET_NAME=tourism-kb

BGE_M3_PATH=D:\AI_models\models\bge-m3
BGE_DEVICE=cuda:0

TEXT_RERANK_MODEL=BAAI/bge-reranker-v2-m3
```

## 前端入口说明

### 广告首页
- 白色主体
- 国际化文案
- 粒子场 + 轻失重效果
- 点击入口弹登录 demo

### 登录 demo
- 不校验账号密码
- 点击登录直接进入系统

### 首页内品牌
- 浏览器标题：`RANGER KNOWLEDGE`
- 标签图标与首页图标统一使用项目自有彩色旅行图标

## 测试

### 后端

```powershell
.venv\Scripts\python.exe -m pytest test\test_api.py -q
```

### 前端

```powershell
cd web
npm run build
```

### 手工全链路导入测试

```powershell
.venv\Scripts\python.exe test\manual_tourism_dataset_flow.py
```

测试报告输出目录：
- `test_output/`

## 当前建议阅读顺序

如果你第一次接手这个项目，建议按这个顺序看：

1. `README.md`
2. `api/knowledge.py`
3. `graphs/graph_builder.py`
4. `core/tourism_metadata.py`
5. `web/src/App.vue`
6. `web/src/components/landing/LandingPortal.vue`
7. `web/src/components/chat/ChatView.vue`
8. `web/src/components/knowledge/KnowledgeUpload.vue`

## 备注

- 当前前端和 README 已经对齐到实际行为
- 运行时模型切换只适配 OpenAI 兼容接口
- 旅游场景建议优先使用支持视觉的模型
