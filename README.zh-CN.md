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
- Telegram 回复会把常见 Markdown 转成富文本显示，并在等待模型时显示动态等待提示。
- 可选受控命令入口：`/run` 读取当前项目本机目录，`/ssh` 读取项目配置的远程服务器，
  输出会写入当前会话上下文，方便继续让模型分析日志和实验结果。
- 普通对话可以自动调用同一套只读命令能力。例如你直接问“看一下服务器训练结果”，
  模型会先读取远程日志/产物，再给出判断。
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
- `/history` 提取当前 Codex 桌面端会话的完整气泡样式 HTML 历史导出。
- `/model` 查看或切换当前 GPT 模型。
- `/new Title` 在当前项目中新建会话。
- `/rename Title` 重命名当前会话。
- `/status` 查看当前项目、会话和模型。
- `/run 命令` 在当前项目本机目录执行只读命令。
- `/ssh 命令` 在当前项目配置的远程服务器执行只读命令。
- 普通对话会在需要时自动调用同一套只读 `/run` / `/ssh` 能力。
- `/exit` 退出当前对话，普通消息会暂停发送给模型。
- `/whoami` 查看你的 Telegram user id。
- `/claim token` 在配置了 `BOT_SETUP_TOKEN` 时授权当前账号。

也可以直接输入 `exit`、`退出` 或 `退出对话`，效果等同于 `/exit`。退出后发送 `/start`、
`/projects` 或 `/sessions` 可以重新进入。

## 配置

环境变量：

| 名称 | 是否必需 | 说明 |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | 是 | 来自 Telegram BotFather 的 token。 |
| `OPENAI_API_KEY` | 是 | OpenAI API key。 |
| `TELEGRAM_ALLOWED_USER_IDS` | 推荐 | 允许使用 bot 的 Telegram user id，多个 id 用逗号分隔。 |
| `BOT_SETUP_TOKEN` | 可选 | 首次 `/claim` 使用的私有授权 token。 |
| `OPENAI_MODEL` | 可选 | 默认是 `gpt-5.4-mini`。 |
| `OPENAI_MODEL_CHOICES` | 可选 | `/model` 中可选择的模型，多个模型用逗号分隔。 |
| `OPENAI_BASE_URL` | 可选 | OpenAI 兼容网关或代理的 API base URL。 |
| `OPENAI_STORE` | 可选 | 默认是 `false`；历史记录保存在本地 SQLite。 |
| `POCKET_CODEX_DATA_DIR` | 可选 | 默认是 `./data`。 |
| `POCKET_CODEX_PROJECTS_FILE` | 可选 | 默认是 `./config/projects.json`。 |
| `MAX_HISTORY_MESSAGES` | 可选 | 默认是 `24`。 |
| `TELEGRAM_HISTORY_ON_OPEN_MESSAGES` | 可选 | 打开 Codex 会话时内联发送的最近消息数，默认是 `30`。 |
| `TELEGRAM_HISTORY_EXPORT_MAX_MESSAGES` | 可选 | HTML 历史导出的最大消息数，默认是 `1000`。 |
| `CODEX_SYNC_ENABLED` | 可选 | 默认是 `true`。 |
| `CODEX_HOME` | 可选 | 默认是当前用户的 `.codex` 目录。 |
| `POCKET_CODEX_COMMANDS_ENABLED` | 可选 | 默认是 `false`。开启后仍需单个项目设置 `allow_shell=true`。 |
| `POCKET_CODEX_COMMAND_TIMEOUT_SECONDS` | 可选 | `/run` 和 `/ssh` 超时秒数，默认是 `60`。 |
| `POCKET_CODEX_COMMAND_OUTPUT_MAX_CHARS` | 可选 | 应用层命令输出预算，默认 `0` 表示不做应用层截断。 |
| `POCKET_CODEX_COMMAND_INLINE_MAX_CHARS` | 可选 | Telegram 单条命令输出分块大小，默认是 `3500`。 |

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
    "system_prompt": "This session is for the steel_cxx project.",
    "allow_shell": false,
    "ssh_target": "user@example.com",
    "ssh_remote_path": "/srv/steel_cxx",
    "ssh_executable": "ssh",
    "ssh_hostkey": "",
    "ssh_password_env": "STEEL_CXX_SSH_PASSWORD"
  }
]
```

项目路径会作为项目元信息传给模型。命令执行默认关闭；只有同时设置
`POCKET_CODEX_COMMANDS_ENABLED=true` 和项目级 `allow_shell=true` 后，
`/run`、`/ssh` 才能使用。命令入口按只读场景设计，会拦截删除、移动、安装、重启、
Git 破坏性操作和输出重定向，并设置超时。Telegram 长输出会自动分段或作为文本附件发送。

开启 Codex 同步后，`/sessions` 会优先列出所选项目路径匹配的 Codex 桌面端会话。
通过 Telegram 发送的新消息会带着 `[Telegram]` 标记追加到选中的 Codex rollout 文件，
这样桌面端恢复这条会话时可以继承手机端的上下文。

选择 Codex 会话时，Pocket Codex 会发送一份左右气泡样式的 HTML 历史文件，方便在手机上
查看电脑端和手机端的完整上下文。导出文件会把 Codex rollout 里的图片转成内嵌缩略图，
包括你发给 Codex 的截图和已经落盘的 Codex 生成图。之后可以用 `/history`
重新获取导出文件。

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
- 如果开启 `/run` 或 `/ssh`，只给可信项目打开 `allow_shell=true`，不要把 SSH 密码提交到 Git。

更多内容见 [docs/security.md](docs/security.md) 和 [docs/windows-startup.md](docs/windows-startup.md)。
完整安装和部署流程见 [docs/deployment.md](docs/deployment.md)。

## 路线图

见 [docs/roadmap.md](docs/roadmap.md)。下一步计划是加入更细的命令授权策略和
Telegram 语音消息支持。

## 发布

见 [docs/github-publish.md](docs/github-publish.md)，里面有安全发布到 GitHub 的步骤。
