# Changelog

## Unreleased

### Breaking changes

- 默认 provider ID 和显示名称由 `newapi` / `New API` 改为 `MyProvider`，OpenCode 和 Codex 均受影响。已有的 `opencode.json` provider 键和 Codex `config.toml` 中的 `[model_providers.newapi]` 不会自动迁移：旧 Codex 配置会与新 `[model_providers.MyProvider]` 段落并存，需要手动清理旧段落。
- `--context` 由仅接受单个值改为接受逗号分隔的多个值；`258,000` 这类千位分隔写法现在会被拒绝。

### Other changes

- 新增 `--insecure` 与 `SWITCH_MODEL_INSECURE=true`，对三种模式统一跳过模型列表请求的 TLS 证书校验；OpenCode 同步器同样收到该选项。默认保持校验，开启时输出警告。
- 新增 `~/.config/api-keys/default.provider`，文件内容作为 OpenCode provider 名称；命令行位置参数优先。
- 请求模型列表时通过 `curl --config -` 从 stdin 传递认证头，不再写入临时文件，API Key 不出现在磁盘或进程参数中。
- `--context` 支持逗号分隔的多个值，并为每个小于原生窗口的值生成一个 capped 子模式；重复值合并。
- 本地 OpenCode cache 与内嵌 snapshot 使用同一套完整性校验；截断或残缺的 cache 会回退到下一个 catalog 来源，不再被静默接受。
- `bailian` / `dashscope` provider 类型实现 `enableThinking` / `thinkingBudget` provider 选项，不再输出 `reasoningEffort` variants，行为与帮助文本一致。
- DeepSeek 分组改用 `@ai-sdk/openai-compatible` 传输，并在官方目录条目声明 `reasoning` 且 `reasoning_options` 含 `toggle` 时生成模型级 `options.thinking`。此前原生 DeepSeek SDK 按固定命名空间读取选项，而生成的 provider ID 带前缀，`thinking` 与 `reasoningEffort` 会被静默丢弃。重新执行原切换命令才会更新已有配置。
- 报告中的 `generator_version` 改为由 `VERSION` 文件在构建时注入，移除硬编码。
- 模型列表响应的非 UTF-8 解码和读取异常统一转换为受控错误，不再输出裸 traceback。
- 拒绝将测试 fixture 或不完整模型目录作为正式内嵌 catalog。
- 本地 cache 缺失且内嵌 catalog 不完整时，恢复到 `opencode models --verbose --pure` 回退。
- 支持从 `~/.config/api-keys/default.url` 读取默认模型服务 URL。
- 保留 Python 3 fallback，并移除 OpenCode provider 替换确认门槛。

## 0.1.0rc1

- 建立独立公开预览基线。
- 移除个人服务默认值，要求显式模型服务 URL。
- Preview 不再显示 API Key 前缀或写入持久 OpenCode 报告。
- OpenCode 写入前创建配置备份。
- 构建改为使用显式、可审计的固定 catalog 输入。
- 将安全回归测试纳入项目测试目录。
