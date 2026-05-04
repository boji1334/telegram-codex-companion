# Pocket Codex

[English](README.md) | [简体中文](README.zh-CN.md)

Pocket Codex 是一个私有 Telegram 对话助手，用来在长期项目中和 OpenAI 持续对话。
它适合部署在一台个人常开电脑上：手机通过 Telegram 发消息，电脑轮询 Telegram，
把会话状态保存在本地 SQLite，并调用 OpenAI API 生成回复。

默认部署不需要公网 IP，也不需要开放本地端口。

## 功能

- 私有 Telegram Bot 入口，支持 iPhone、Android、桌面 Telegram 和 Web Telegram。
- 通过 Telegram 内联按钮切换项目和会话。
- 可选 Codex 桌面端同步：列出本机 Codex threads，读取历史，并把 Telegram
  对话追加回选中的 rollout。
- 气泡样式 HTML 历史导出会内嵌图片缩略图，手机上可以看到你发送的截图和 Codex 生成图。
- 使用 SQLite 在你自己的电脑上保存对话历史。
- 支持用户白名单和首次 `/claim` 授权流程。
- 使用 OpenAI Responses API 作为模型后端。
- 包含测试、lint、文档和 CI，适合发布到 GitHub。

## 架构

```text
iPhone 上的 Telegram
  -> Telegram Bot API
  -> 运行在常开电脑上的 Pocket Codex
  -> SQLite 本地历史记录
  -> OpenAI Responses API
```

## 快速开始

完整部署步骤见 [docs/deployment.md](docs/deployment.md)。

1. 通过 [BotFather](https://t.me/BotFather) 创建一个 Telegram bot。
2. 安装 Anaconda 或 Miniconda。
3. 创建项目本地 Conda 环境：

```powershell
conda env create -p .\.conda -f environment.yml
.\.conda\python.exe -m pip --version
```

4. 从 `.env.example` 创建 `.env`，并填入：

```env
TELEGRAM_BOT_TOKEN=your-telegram-token
OPENAI_API_KEY=your-openai-key
TELEGRAM_ALLOWED_USER_IDS=your-numeric-telegram-user-id
```

5. 创建项目配置：

```powershell
Copy-Item .\config\projects.example.json .\config\projects.json
```

6. 启动 bot：

```powershell
.\.conda\python.exe -m pocket_codex --check-config
.\.conda\python.exe -m pocket_codex
```

之后也可以用脚本启动：

```powershell
.\scripts\run-pocket-codex.ps1
```

7. 打开 Telegram，给你的 bot 发送 `/start`。

## Telegram 命令

- `/start` 连接已授权账号。
- `/projects` 打开项目选择器。
- `/sessions` 打开当前项目的会话选择器。
- `/history` 从当前 Codex 桌面端会话加载最近历史。
- `/history all` 发送当前会话的完整气泡样式 HTML 历史导出。
- `/new Title` 在当前项目中新建会话。
- `/rename Title` 重命名当前会话。
- `/status` 查看当前项目、会话和模型。
- `/whoami` 查看你的 Telegram user id。
- `/claim token` 在配置了 `BOT_SETUP_TOKEN` 时授权当前账号。

## 配置

环境变量：

| 名称 | 是否必需 | 说明 |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | 是 | 来自 Telegram BotFather 的 token。 |
| `OPENAI_API_KEY` | 是 | OpenAI API key。 |
| `TELEGRAM_ALLOWED_USER_IDS` | 推荐 | 允许使用 bot 的 Telegram user id，多个 id 用逗号分隔。 |
| `BOT_SETUP_TOKEN` | 可选 | 首次 `/claim` 使用的私有授权 token。 |
| `OPENAI_MODEL` | 可选 | 默认是 `gpt-5.4-mini`。 |
| `OPENAI_BASE_URL` | 可选 | OpenAI 兼容网关或代理的 API base URL。 |
| `OPENAI_STORE` | 可选 | 默认是 `false`；历史记录保存在本地 SQLite。 |
| `POCKET_CODEX_DATA_DIR` | 可选 | 默认是 `./data`。 |
| `POCKET_CODEX_PROJECTS_FILE` | 可选 | 默认是 `./config/projects.json`。 |
| `MAX_HISTORY_MESSAGES` | 可选 | 默认是 `24`。 |
| `TELEGRAM_HISTORY_ON_OPEN_MESSAGES` | 可选 | 打开 Codex 会话时内联发送的最近消息数，默认是 `30`。 |
| `TELEGRAM_HISTORY_EXPORT_MAX_MESSAGES` | 可选 | HTML 历史导出的最大消息数，默认是 `1000`。 |
| `CODEX_SYNC_ENABLED` | 可选 | 默认是 `true`。 |
| `CODEX_HOME` | 可选 | 默认是当前用户的 `.codex` 目录。 |

项目配置示例：

```json
[
  {
    "id": "general",
    "name": "General Chat",
    "path": null,
    "system_prompt": "General personal conversation. Answer in the user's preferred language."
  },
  {
    "id": "steel_cxx",
    "name": "steel_cxx",
    "path": "C:/Users/you/Documents/steel_cxx",
    "system_prompt": "This session is for the steel_cxx project."
  }
]
```

项目路径会作为项目元信息传给模型。第一版不会自动读取文件，这样安全边界更清楚。
文件搜索和显式文件附件工具可以作为独立模块继续添加。

开启 Codex 同步后，`/sessions` 会优先列出所选项目路径匹配的 Codex 桌面端会话。
通过 Telegram 发送的新消息会带着 `[Telegram]` 标记追加到选中的 Codex rollout 文件，
这样桌面端恢复这条会话时可以继承手机端的上下文。

选择 Codex 会话时，Pocket Codex 会发送一份左右气泡样式的 HTML 历史文件，方便在手机上
查看电脑端和手机端的完整上下文。导出文件会把 Codex rollout 里的图片转成内嵌缩略图，
包括你发给 Codex 的截图和已经落盘的 Codex 生成图。之后也可以用 `/history` 重新加载
最近纯文本历史，或用 `/history all` 重新获取导出文件。

## 开发

```powershell
python -m pip install -e ".[dev]"
ruff check .
pytest
```

## 安全说明

- 不要提交 `.env`、API key、Telegram token 或 SQLite 数据库。
- 单用户部署时，优先使用 `TELEGRAM_ALLOWED_USER_IDS`。
- 如果偏好 `/claim` 流程，请使用足够长的随机 `BOT_SETUP_TOKEN`。
- 家用部署建议保持轮询模式，除非你明确需要 webhook。
- 项目目录通过 `config/projects.json` 白名单控制。

更多内容见 [docs/security.md](docs/security.md) 和 [docs/windows-startup.md](docs/windows-startup.md)。
完整安装和部署流程见 [docs/deployment.md](docs/deployment.md)。

## 路线图

见 [docs/roadmap.md](docs/roadmap.md)。下一步计划是支持在白名单项目目录中显式读取文件，
之后加入 Telegram 语音消息支持。

## 发布

见 [docs/github-publish.md](docs/github-publish.md)，里面有安全发布到 GitHub 的步骤。
