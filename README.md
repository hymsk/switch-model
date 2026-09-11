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

## Provider 名称

OpenCode 与 Codex 的默认 provider ID 和显示名称均为 `MyProvider`。可将默认 OpenCode provider 名称写入 `~/.config/api-keys/default.provider`，文件仅包含一行名称：

```text
CompanyGateway
```

优先级为命令行位置参数、`~/.config/api-keys/default.provider`、内置默认值 `MyProvider`。文件存在时，其内容同时用作 provider ID 和显示名称。

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

请求模型列表时，API Key 通过 `curl --config -` 从 stdin 传入，既不写入临时文件，也不出现在进程参数列表中。

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

> **注意**：写入会替换 `opencode.json` 中的整个 `provider` 对象。原有其他 provider（例如 `anthropic`、`openai`）不会被保留，只写入本次同步生成的 provider。写入前会创建带时间戳的备份。

OpenCode 还支持：

```text
--context <tokens>[,<tokens>...]
--mapping-file <path>
--no-prefix-fallback
```

`--context` 接受一个或多个逗号分隔的上下文长度：`258000`、`258k` 或 `258K`。每个小于模型原生窗口的值都会生成一个 capped 子模式；重复值会合并。不接受千位分隔（`258,000`）。`0` 表示不生成上下文子模式。

### Catalog 与模型匹配

写入前先刷新本地 OpenCode catalog，使匹配基于当前发布的模型目录：

```bash
opencode models --refresh --pure
```

刷新失败只警告并继续使用现有 cache，离线环境仍可运行。设置 `OPENCODE_CATALOG_REFRESH=false` 可跳过刷新。Catalog 运行时顺序为：刷新本地 cache -> 本地 cache -> 内嵌完整 snapshot -> 实时查询。

本地 cache 与内嵌 snapshot 使用同一套完整性校验：少于 10 个 provider、少于 100 个模型或普遍缺少 limit 的目录会被拒绝，并自动回退到下一个来源。这样截断或损坏的 cache 不会被静默当作完整目录使用。

每个远端模型按以下状态之一匹配到 catalog 条目：

| 状态 | 含义 |
| --- | --- |
| `matched` | 唯一命中，继承完整 limit、capabilities 和 variants |
| `mapped` | 由 `--mapping-file` 显式指定，或命中内置原厂别名 |
| `guessed` | 精确匹配失败后按前缀族回退 |
| `ambiguous` | 多个候选同分且元数据不同，取排序第一项兜底 |
| `unmatched` | catalog 中不存在，不生成 limit |

`ambiguous` 会在报告中保留全部竞争候选、实际选中的来源和提示 `--mapping-file` 的警告；`--strict` 仍将其视为不完整。需要固定某个来源时使用映射文件：

默认评分先比较模型身份：精确 model/full/API ID（400）> 标点归一化（300）> Zen free 别名（200）> effort 基础模型（100）。同一精度内优先模型原厂（如 OpenAI、DeepSeek、Moonshot AI、智谱），其次 Alibaba / Alibaba CN，最后其他渠道；远端 ID 中的渠道前缀不再获得优先权。原厂加 60 分、后续原厂区域加 50 分，Alibaba 加 30 分、Alibaba CN 加 20 分；Qwen 的原厂就是 Alibaba。元数据完整度最多加 7 分，active 加 1 分，不以窗口大小或是否支持推理衡量渠道质量。前缀回退先保留最长的同版本前缀，再使用相同渠道优先级。显式映射始终优先。

这些规则选择的是 **catalog 元数据来源**，不是 API 网络路由。请求仍发送到配置的 `baseURL`，模型 ID 保持不变；不会验证或改变网关内部的上游渠道。原厂 limit 也不保证中转服务支持相同窗口。同分且元数据不同仍保留 `ambiguous` 提示，不宣称已找到实测最佳渠道。

```json
{
  "workbuddy/deepseek-v4.1-flash": "opencode-go/deepseek-v4.1-flash"
}
```

内置别名：`deepseek-v4.1-flash`（含渠道前缀、忽略大小写）优先映射到 `deepseek/deepseek-flash`（原厂显示名称为 DeepSeek V4.1 Flash），高于普通评分，报告规则为 `official-flash-alias`。这是同一模型的 ID 别名，不是回退到旧版 `deepseek-v4-flash`。仅继承元数据，不修改远端模型 ID；显式 `--mapping-file` 仍优先。原厂条目不存在时恢复普通匹配，不扩展到其他版本或 Pro 模型。

### Provider 类型与推理配置

`--provider-type` 决定 npm 包和推理参数的表达方式：

| 类型 | npm 包 | 推理配置 |
| --- | --- | --- |
| `openai-compatible` | `@ai-sdk/openai-compatible` | 模型级 `variants`，使用 `reasoningEffort` |
| `bailian` / `dashscope` | `@ai-sdk/alibaba` | provider 级 `enableThinking` / `thinkingBudget` |
| `auto-group` | 按 catalog providerID 决定 | 每个分组使用 `openai-compatible` 语义 |

阿里云系模型（`alibaba`、`alibaba-cn`）用「开关」和「token 预算」描述思考能力，没有 `low`/`medium`/`high` 档位，因此 `bailian`/`dashscope` 模式不输出 `reasoningEffort` variants，而是生成：

- `reasoning_options` 含 `toggle` → `enableThinking: true`
- `reasoning_options` 含带数值 `max` 的 `budget_tokens` → `enableThinking: true` 和 `thinkingBudget: <max>`
- `budget_tokens` 无数值 `max` → 回退为 `enableThinking: true` 并记录警告

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

构建不会运行 `opencode models --refresh`。刷新只在运行时发生，即用户实际执行 `switch-model.sh opencode` 时。

## 验证

```bash
bash -n build.sh shell/*.sh switch-model.sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

## License

Licensed under `AGPL-3.0-or-later`.
