# switch-model

`switch-model` 从 OpenAI-compatible `/v1/models` endpoint 获取模型列表，并更新 Claude Code、Codex 或 OpenCode 的本地配置。

项目同时维护模块化源码和单文件分发产物：

```text
build.sh             # 从源码生成 switch-model.sh
shell/               # Bash 模块
python/              # 内嵌 Python 模块
switch-model.sh      # 生成的单文件 CLI
tests/               # 离线测试与最小 catalog fixture
```

## 要求

- Bash
- Python 3.8 或更高版本
- `curl`
- Claude Code、Codex 或 OpenCode 的本地配置目录
- OpenAI-compatible 模型服务 URL 和 API Key 文件

本项目不配置默认在线服务。可将默认 URL 写入 `~/.config/api-keys/default.url`，文件仅包含一行 URL：

```text
https://api.example.com
```

设置后可省略命令行 URL。优先级为命令行 URL、`SWITCH_MODEL_BASE_URL`、`~/.config/api-keys/default.url`。

## API Key

默认读取：

```text
~/.config/api-keys/default.sk
```

也可以显式指定：

```bash
bash switch-model.sh claude https://api.example.com --sk-file ~/.config/api-keys/work.sk --preview
```

API Key 文件建议使用 `0600` 权限。Preview 和错误输出不会显示 Key 或 Key 前缀。

Claude Code 和 Codex 的目标配置会保存实际 Key；其备份也包含 Key。OpenCode 默认写入 `{file:...}` 引用，不把 Key 值写入主配置。

## 使用

Claude Code：

```bash
bash switch-model.sh claude https://api.example.com
bash switch-model.sh claude https://api.example.com opus --preview
```

Codex：

```bash
bash switch-model.sh codex https://api.example.com
bash switch-model.sh codex https://api.example.com gpt --preview
```

OpenCode：

```bash
# Preview 不修改 Host 配置，也不写持久报告。
bash switch-model.sh opencode https://api.example.com --preview

# 写入会先创建备份，再替换 opencode.json 中的整个 provider 对象。
bash switch-model.sh opencode https://api.example.com
```

OpenCode 还支持：

```text
--context <tokens>
--mapping-file <path>
--no-prefix-fallback
```

`--context` 仅接受单个上下文长度：`258000`、`258k` 或 `258K`。不支持逗号分隔、千位分隔或多个值。`0` 表示不生成上下文子模式。

## 配置影响

| 模式 | 读取 | 写入 |
| --- | --- | --- |
| Claude Code | API Key、`~/.claude/settings.json`、远端 models | Claude settings 和时间戳备份 |
| Codex | API Key、Codex 配置、远端 models | `auth.json`、`config.toml` 和时间戳备份 |
| OpenCode Preview | API Key、OpenCode catalog、远端 models | 仅安全临时文件，退出前删除 |
| OpenCode Write | API Key、OpenCode config/catalog、远端 models | OpenCode config、单份备份和匹配报告 |

模型服务请求、认证失败或空模型列表会显式失败，不会静默回退到一个可能不可用的默认模型。

## 构建

默认只复用 Git `HEAD:switch-model.sh` 中已审计的完整 catalog；不会信任工作区中的 dirty 生成物，也不会读取开发机 cache：

```bash
bash build.sh
```

首次构建、更新 catalog，或 Git `HEAD` 中仍是旧的不完整快照时，必须显式指定已审计的完整 OpenCode catalog。构建会拒绝只含少量 provider/model 或普遍缺少 `limit` 的 fixture/部分目录：

```bash
OPENCODE_MODELS_FILE=/path/to/reviewed-models.json bash build.sh
```

构建不会运行 `opencode models --refresh`。

## 验证

```bash
bash -n build.sh shell/*.sh switch-model.sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

## License

Licensed under `AGPL-3.0-or-later`.
