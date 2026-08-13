# Dify 文档批量上传工具

基于 [Dify](https://github.com/langgenius/dify) 知识库 API 对文档进行批量上传&解析的工具。

Dify 知识库上传界面在批量上传大量文件时操作较繁琐。本工具可自动遍历指定目录及子目录，逐个将文档上传至 Dify 知识库，并轮询索引状态直至完成。在需要上传大量文件时，可减少手动分批上传与等待解析的耗时。

> 🌐 **[在线宣传页](https://samge0.github.io/dify-upload/)** — 可视化了解功能特性与工作流程

## 功能特性

- ✅ **批量上传** - 自动遍历目录上传文档到 Dify 知识库
- ✅ **索引轮询** - 上传后通过官方 API 轮询索引进度，完成后再处理下一个文件
- ✅ **进度记录** - 自动记录每个文件的处理状态，中断后重新运行会跳过已完成的文件
- ✅ **去重兜底** - 即使进度记录丢失，也会通过 API 查询文档是否已存在，避免重复上传
- ✅ **元数据管理** - 支持为文档设置自定义元数据（`.meta.json` 同名文件）
- ✅ **自动建库** - 可选：知识库不存在时按名称自动创建
- ✅ **纯 API 模式** - 无需数据库依赖，仅凭一个 `dataset-` 开头的 API Key 即可运行
- ✅ **API 请求日志** - 独立记录每次 Dify API 请求（地址 / 请求头脱敏 / 请求体 / 响应），便于排查问题
- ✅ **GUI 客户端** - 提供 customtkinter 图形界面，可打包为单文件可执行程序

## 独立客户端

可以在 [Releases](https://github.com/Samge0/dify-upload/releases) 下载编译好的客户端，启动后直接在图形界面填写配置即可，无需手动编辑配置文件。

如果想要自己构建 `Windows / macOS / Linux` 系统下的可执行程序，可参考 [scripts/README.md](scripts/README.md) 中的说明进行构建。

## 系统要求

- Python 3.13+
- Dify（自建或 Cloud，需开启知识库 API）

> 兼容性：本工具已在 **Dify 1.13.3** 版本测试可用；其它版本未测试，请自行验证（知识库 API 在不同版本间可能存在差异）。

## 安装

### 1. 克隆项目

```bash
git clone https://github.com/Samge0/dify-upload.git
cd dify-upload
```

### 2. 创建环境

```bash
# 使用 miniconda
conda create -n dify-upload python=3.13 -y
conda activate dify-upload

# 或使用 uv
uv venv --python 3.13
# Windows: .\.venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt

# 或使用 uv
uv pip install -r requirements.txt
```

## 配置

> 注：以下配置方式适用于**源码运行**。如果使用 [Releases](https://github.com/Samge0/dify-upload/releases) 中的打包客户端，启动后直接在图形界面填写配置即可。

源码运行时，先将 `difys/configs.demo.py` 复制为 `difys/configs.py`，然后编辑 `configs.py`：

```python
# Dify API 配置
API_URL = 'http://localhost/v1'           # API 地址（需含 /v1）
API_KEY = 'dataset-xxxxxx'                # API Key（dataset- 开头）
DATASET_ID = ''                           # 知识库ID（留空则按 DATASET_NAME 查找/创建）
DATASET_NAME = 'my_dataset'               # 知识库名称
AUTO_CREATE_DATASET = False               # 知识库不存在时按名称自动创建

# 索引与分段配置（三者受联动约束，详见下文「索引与分段配置」）
INDEXING_TECHNIQUE = 'economy'            # 索引模式：high_quality | economy
DOC_FORM = 'text_model'                   # 分段模式：text_model | hierarchical_model | qa_model
PROCESS_RULE_MODE = 'automatic'           # 分段处理规则：automatic | custom | hierarchical
DOC_LANGUAGE = ''                         # 文档语言；留空走 Dify 默认（可选值见下文）
SEGMENT_SEPARATOR = '\\n\\n'              # 分段分隔符（custom/hierarchical 父分段；用 \n 表示换行）
SEGMENT_MAX_TOKENS = 500                  # 每段最大 token（custom/hierarchical 父分段）
SEGMENT_CHUNK_OVERLAP = 0                 # 分段间重叠 token（custom/hierarchical 父分段）
PREPROCESS_REMOVE_EXTRA_SPACES = True     # 预处理：去除多余空格
PREPROCESS_REMOVE_URLS_EMAILS = False     # 预处理：去除 URL/邮箱
PREPROCESS_REMOVE_STOPWORDS = False       # 预处理：去除停用词
HIERARCHICAL_PARENT_MODE = 'paragraph'    # 父子模式父分段方式：full-doc | paragraph（仅 hierarchical）
HIERARCHICAL_CHILD_SEPARATOR = '\n'       # 父子模式子分段分隔符（仅 hierarchical）
HIERARCHICAL_CHILD_MAX_TOKENS = 200       # 父子模式子分段最大 token（仅 hierarchical）

# 文档来源与过滤
DOC_DIR = '/path/to/documents'            # 文档目录
DOC_SUFFIX = 'md,txt,pdf,docx'            # 支持的文件后缀
DOC_MIN_LINES = 1                         # 最小文件行数（仅 txt/md/html 生效）
DOC_MAX_SIZE_MB = 15                      # 单文件大小上限（MB），超过跳过

# 运行行为
ONLY_UPLOAD = False                       # 仅创建文档，不轮询等待索引完成
PROGRESS_CHECK_INTERVAL = 5               # 索引进度检查间隔（秒）
ENABLE_PROGRESS_LOG = True                # 打印索引进度日志
FIRST_INDEX_WAIT_TIME = 0                 # 首次上传后索引等待时间（秒）
INDEXING_MAX_WAIT = 3600                  # 单个文件索引等待上限（秒）；qa_model/摘要生成较慢时可调大
ENABLE_API_LOG = True                     # 记录 Dify API 完整请求日志（独立文件，敏感字段脱敏）

# 元数据
METADATA_SUFFIX = '.meta.json'            # 元数据文件后缀（替换文档后缀，如 a.md -> a.meta.json）
```

### 获取 API Key

在 Dify 知识库页面点击「**API**」入口（或访问 `{你的 Dify 地址}/datasets/api`），创建一个 API Key（`dataset-` 开头），配置到 `API_KEY`。

## 使用方法

### 基本使用

在项目根目录执行：

```bash
# Python 方式
python -m difys.main

# uv 方式
uv run python -m difys.main
```

### 准备文档

1. 将文档放入配置的 `DOC_DIR` 目录
2. 支持的文件格式：`.md`, `.txt`, `.pdf`, `.docx` 等（由 `DOC_SUFFIX` 控制）
3. （可选）为文档添加元数据文件

### 元数据文件

如需为文档添加元数据，创建同名但替换后缀为 `.meta.json` 的文件：

```
documents/
├── report.pdf
├── report.meta.json    # report.pdf 的元数据
├── manual.docx
└── manual.meta.json    # manual.docx 的元数据
```

元数据文件为扁平 JSON，工具会自动按 key 创建知识库元数据字段并赋值：

```json
{
  "author": "张三",
  "category": "技术文档",
  "version": 1
}
```

## 索引模式

| 模式 | 说明 |
|------|------|
| `high_quality` | 高质量索引，使用嵌入模型，适合精确语义检索 |
| `economy` | 经济索引，基于关键词，资源占用更低 |

> 注意：
> - `indexing_technique` 在向知识库添加**第一个文档**时为必填项，后续文档会继承知识库的索引模式。
> - **索引模式在知识库创建后默认不可修改**：只要知识库**里还有文档**就无法切换 `high_quality` ↔ `economy`。若先在 Dify 后台把该库文档**全部清空**，则相当于回到空库状态，可以重新选择索引模式（这与新建一个知识库效果相近）。本工具在提供了 `DATASET_ID` 时会拉取目标库的实际索引模式与配置比对，不一致则提前阻断。
> - **关于 15MB 单文件上限**：这是 Dify 的默认限制（`UPLOAD_FILE_SIZE_LIMIT`）。若是**自部署** Dify，可在服务端环境变量/配置中调大该值；本工具的 `DOC_MAX_SIZE_MB` 仅用于**本地预过滤**（超过则在客户端直接跳过，不发起上传），把它设成大于服务端限制的值意义不大——真正的上限仍以你的 Dify 服务端为准。

### 关于「摘要自动生成」

> ⚠️ 路径：`Dify 管理后台 - 知识库 - 设置 - 摘要自动生成`，默认**禁用**。
>
> 启用后，Dify 会为新添加的文档**自动生成摘要**，**索引构建时间会大幅增加**（本工具会相应地轮询等待更久，单个文件的 `indexing` 阶段可能明显变长，属正常现象）。如非必要建议保持禁用以加快入库速度；已有文档的摘要仍可在 Dify 界面-知识库设置中手动开启。

## 索引与分段配置

「索引模式 / 分段模式 / 分段处理规则」三者**层层联动**，本工具在 GUI 中会按上游选择动态收紧下游可选项；源码运行时则由启动校验提示，必要时会对不符合要求的配置进行阻断。

### 约束矩阵（唯一合法组合）

| 索引模式 `INDEXING_TECHNIQUE` | 分段模式 `DOC_FORM` | 分段处理规则 `PROCESS_RULE_MODE` | 说明 |
|---|---|---|---|
| `high_quality` | `text_model` | `automatic` 或 `custom` | 标准文本分段（默认） |
| `high_quality` | `hierarchical_model` | **`hierarchical`（锁定）** | 父子分段：父分段粗粒度召回、子分段细粒度匹配 |
| `high_quality` | `qa_model` | `automatic` 或 `custom` | 问答对提取（需 Dify 后台配问答模型） |
| `economy` | `text_model` | `automatic` 或 `custom` | 经济索引，不含父子/问答 |
| `economy` | `qa_model` | `automatic` 或 `custom` | 经济索引下的问答对提取 |

要点：
- **`hierarchical_model` 与 `hierarchical` 是一对一锁定**——选了「分段模式 = 父子」就自动锁定「分段处理规则 = hierarchical」，反之亦然。
- **父子模式仅在 `high_quality` 下可用**：索引模式切到 `economy` 时，父子相关选项会被自动剔除。
- 索引/分段模式在知识库**有文档时不可修改**（见上文「索引模式」注意事项）；如需切换，请先在 Dify 后台清空文档或新建知识库。

### 参数说明

| 配置项 | 作用 | 适用模式 |
|---|---|---|
| `INDEXING_TECHNIQUE` | 索引模式：`high_quality` 用嵌入模型（精确语义检索）；`economy` 基于关键词（省资源） | 全部（首文档必填） |
| `DOC_FORM` | 分段模式：`text_model` 文本 / `hierarchical_model` 父子 / `qa_model` 问答对 | 全部 |
| `PROCESS_RULE_MODE` | 分段处理规则：`automatic` 内置规则 / `custom` 自定义 / `hierarchical` 父子 | 全部 |
| `SEGMENT_SEPARATOR` | 分段分隔符（用 `\n` 表示换行） | custom / hierarchical（父分段） |
| `SEGMENT_MAX_TOKENS` | 每段最大 token 数 | custom / hierarchical（父分段） |
| `SEGMENT_CHUNK_OVERLAP` | 相邻分段间的重叠 token 数 | custom / hierarchical（父分段） |
| `HIERARCHICAL_PARENT_MODE` | 父分段方式：`full-doc` 整篇为父 / `paragraph` 按段落为父 | 仅 hierarchical |
| `HIERARCHICAL_CHILD_SEPARATOR` | 子分段分隔符 | 仅 hierarchical |
| `HIERARCHICAL_CHILD_MAX_TOKENS` | 子分段最大 token 数 | 仅 hierarchical |
| `PREPROCESS_REMOVE_EXTRA_SPACES` | 预处理：去除多余空格 | custom / hierarchical |
| `PREPROCESS_REMOVE_URLS_EMAILS` | 预处理：去除 URL/邮箱 | custom / hierarchical |
| `PREPROCESS_REMOVE_STOPWORDS` | 预处理：去除停用词 | custom / hierarchical |
| `DOC_LANGUAGE` | 文档语言（见下） | 全部（可选） |
| `DOC_MAX_SIZE_MB` | 单文件大小上限（MB），本地预过滤，超过则跳过 | 全部 |

### 关于 `DOC_LANGUAGE`

主要在**问答（qa_model）/ 父子（hierarchical_model）**模式下影响 Dify 调用 LLM 生成问答对、摘要等内容时所用的**语言**；对纯文本分段（text_model）影响较小。中文文档建议选 `Chinese Simplified`。留空则走 Dify 默认（English）。完整可选值见 `difys/configs.demo.py`（或 GUI 下拉）。

### 硬性约束（不符会在上传前阻断）

> ⚠️
> 1. **父子模式（`hierarchical`）仅在高质量索引下可选**——若选了 `hierarchical` 但 `INDEXING_TECHNIQUE=economy`，运行前直接阻断。
> 2. **向已有知识库上传时模式必须一致**——当提供了 `DATASET_ID` 时，本工具会拉取该库实际的 `indexing_technique` / `doc_form`，与当前配置比对，不一致则提前阻断（避免上传后才在服务端失败）。如需更换模式，请在 Dify 后台清空文档或重新创建知识库，再把新 ID 填到 `DATASET_ID`。
>
> 注：仅按 `DATASET_NAME` 找到（未提供 ID）的既有知识库，**当次运行**不做该比对（首次运行后 ID 会自动回填，下一次起即会校验）。

### 配置方式说明

- **GUI 客户端**：在「分段处理规则 / 分段模式 / 索引模式」下拉切换时，可选项会按约束矩阵**动态收紧**，下方「分段处理规则」区会自动**显示/隐藏**该模式对应的子配置。保存时持久化**全部**字段，切换模式不丢失配置。
- **源码运行**：切换模式后请按启动日志中的 `⚠️` 提示补全必要配置；不合理但可在服务端失败的组合会被**阻断**，其余仅提示。
- 分隔符类字段约定**用 `\n` 表示换行**（如 `\n\n` 表示双换行）。


## 处理进度记录

工具会自动记录每个文件的处理状态（待处理 / 已上传 / 索引中 / 完成 / 失败），中断后重新运行会自动跳过已完成的文件，仅继续处理未完成或失败的文件。

如需重新开始，删除缓存文件：

```bash
# Windows
del ~/.dify_upload/state_*.json

# Linux/Mac
rm ~/.dify_upload/state_*.json
```

或在 GUI 客户端点击「清除进度」按钮。

## API 请求日志

开启 `ENABLE_API_LOG`（默认开启）后，每次 Dify API 请求都会独立记录到日志文件，包含：请求时间、方法、地址、请求头（敏感字段脱敏）、请求体、HTTP 状态码、响应结果、耗时。

- **日志位置**：`~/.dify_upload/api_logs/api_YYYY-MM-DD.log`（按天切割，保留 30 天）
- **敏感字段脱敏**：`auth/token/secret/password` 等命中的请求头或请求体字段，其值保留前 3 + 后 3 字符，中间以 6 个 `*` 拼接；`Authorization: Bearer xxx` 保留 `Bearer ` 前缀，仅对 token 部分脱敏；过短的值整体掩码为 `******`
- **响应中文**：Dify 传输层会对非 ASCII 做 `\uXXXX` 转义，日志会自动还原为真实字符（如中文）
- **关闭方式**：把 `ENABLE_API_LOG` 设为 `False`（源码模式编辑 `difys/configs.py`；GUI 在界面勾选「记录API请求日志」）

> 日志仅写入该独立文件，不输出到主日志流/GUI 界面，避免轮询索引时刷屏。日志记录失败不会影响业务请求。


## 常见问题

<details>
<summary>执行脚本提示: ModuleNotFoundError: No module named 'difys'</summary>

一般在 IDE 中执行不会遇到，直接在终端执行时可能遇到。

解决方法：在项目根目录使用 `-m` 方式运行（无需配置 `PYTHONPATH`）：

```bash
python -m difys.main
```

或手动配置临时环境变量 `PYTHONPATH` 指向当前项目目录：

- Linux/macOS：`export PYTHONPATH=. && python difys/main.py`
- Windows CMD：`set PYTHONPATH=. && python difys/main.py`
- Windows PowerShell：`$env:PYTHONPATH = "."; python difys/main.py`
</details>

<details>
<summary>认证失败或 API 连接错误</summary>

检查 `API_KEY` 是否正确（需 `dataset-` 开头）、是否有效，以及 `API_URL` 是否包含 `/v1`。
</details>

<details>
<summary>提示 indexing_technique is required</summary>

向空知识库添加第一个文档时必须指定 `INDEXING_TECHNIQUE`（`high_quality` 或 `economy`）。
</details>

## 技术支持

- GitHub: https://github.com/Samge0/dify-upload
- Dify 官方文档: https://docs.dify.ai

## 许可证

MIT License
