# Changelog

## Unreleased

- 拒绝将测试 fixture 或不完整模型目录作为正式内嵌 catalog。
- 本地 cache 缺失且内嵌 catalog 不完整时，恢复到 `opencode models --verbose --pure` 回退。
- `--context` 仅支持单个纯数字或 `k`/`K` 后缀的上下文长度，并按总 `limit.context` 生成不扩大 catalog limit 的子模式。
- 保留 Python 3 fallback，并移除 OpenCode provider 替换确认门槛。

## 0.1.0rc1

- 建立独立公开预览基线。
- 移除个人服务默认值，要求显式模型服务 URL。
- Preview 不再显示 API Key 前缀或写入持久 OpenCode 报告。
- OpenCode 写入前创建配置备份。
- 构建改为使用显式、可审计的固定 catalog 输入。
- 将安全回归测试纳入项目测试目录。
