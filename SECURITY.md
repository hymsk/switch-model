# Security Policy

## Reporting

安全问题请使用 GitHub Private Vulnerability Reporting。不要在公开 Issue 中提交 API Key、Host 配置、备份、匹配报告或包含私有模型名称的日志。

## Security Model

- API Key 只从显式文件读取，并通过环境变量或标准输入边界传递给 Python 子进程。
- Preview 不显示 Key 或 Key 前缀。
- Claude Code 和 Codex 配置及其备份可能包含明文 Key。
- OpenCode 写入会先创建配置备份，再替换整个 `provider` 对象。
- 正式构建必须使用已审计的完整 catalog 文件，或复用当前受版本控制生成物中的已审计快照；不得把任意开发机 cache、测试 fixture 或部分 provider 目录嵌入发布产物。

仓库和 Issue 中不得提交 `.sk`、`.env`、`.token`、Host 用户配置或真实服务凭据。
