# 贡献指南

## 开发流程

1. 保持改动聚焦，不混入无关格式化、重命名、依赖升级或其他工作区改动。
2. 修改 `shell/` 或 `python/` 后，重新生成并提交同步的 `switch-model.sh`：

   ```bash
   bash build.sh
   ```

3. 运行验证：

   ```bash
   bash -n build.sh shell/*.sh switch-model.sh
   python3 -m unittest discover -s tests -p 'test_*.py' -v
   git diff --check
   ```

4. 测试必须使用 fixture、临时 `HOME` 和本地 mock server，不得调用真实模型服务或读取开发者配置。
5. 提交前审阅完整 diff，排除生成缓存、凭据、用户配置、本机绝对路径和调试残留。

## 提交消息

本项目采用 [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/)，
并结合 Git、Linux Kernel 与 Angular 等开源项目的可读性规范。提交消息是长期可检索的
变更记录；它必须能在脱离 Pull Request、代码上下文和外部链接的情况下，说明变更的
目的和影响。

根目录的 [`.gitmessage`](./.gitmessage) 是本项目的标准提交模板。首次克隆后执行以下
命令启用该模板；不修改全局 Git 配置：

```bash
git config --local commit.template .gitmessage
```

使用 `git commit`（不带 `-m`）时，Git 会在编辑器中载入模板。以 `#` 开头的说明行会由 Git 自动移除。

### 消息结构

```text
<type>[(<scope>)][!]: <summary>

<body>

<footer(s)>
```

- **标题（header）**：必填，格式严格为 `<type>[(<scope>)][!]: <summary>`；`scope` 和 `!` 可选。标题最多 72 个字符，包含前缀。
- **正文（body）**：标题后必须空一行。对 `feat`、`fix`、`perf`、`refactor`、`build`、安全修复和任何影响公开行为的变更必填；仅包含自明且孤立的 `docs`、`test` 或 `chore` 改动时可省略。
- **页脚（footer）**：可选，正文后空一行。用于破坏性变更、经核实的 Issue/PR 引用以及其他真实 Git trailer；不得伪造验证、审阅、签署或 Issue 信息。

标题、正文和 footer 各部分之间只能用一个空行分隔。普通英文说明每行最多 72 个字符；URL、命令、日志、表格和代码块可超出此限制。

### 标题

`type` 必须为以下小写值之一：

| Type | 使用场景 |
| --- | --- |
| `feat` | 新增用户可见功能。 |
| `fix` | 修复错误行为。 |
| `docs` | 仅修改文档。 |
| `test` | 新增、修正或删除测试。 |
| `refactor` | 不新增功能、不修复错误的代码结构调整。 |
| `perf` | 改善可度量的性能。 |
| `build` | 修改构建、打包或依赖行为。 |
| `ci` | 修改或删除持续集成配置、脚本。 |
| `chore` | 不属于上述类型的维护工作。 |
| `revert` | 回退已存在的提交。 |

`scope` 应是从变更日志读者视角识别受影响区域的稳定名词，而非文件名、分支名或临时
任务名。可选范围为：`shell`、`python`、`opencode`、`codex`、`claude`、`gemini`、
`catalog`、`build`、`tests`、`docs`、`release`、`deps`、`security`。跨区域且不存在
主导范围时省略 `scope`；不得罗列多个范围。

`summary` 必须使用小写英文祈使式，简短描述结果，不加句号。例如使用 `add`、`fix`、
`preserve`、`reject`，而不用 `added`、`fixes`、`fixing` 或无动词的名词短语。标题中
不得使用 emoji、`WIP`、`fixup!`、`squash!`、Issue 引用、验证结果或含糊表述（如
`update stuff`、`misc changes`）。

```text
# 正确
feat(opencode): add explicit context limit
fix(shell): preserve configured endpoint URL
docs: clarify local verification steps
ci: remove GitHub Actions workflow

# 错误
Fixed context limit                         # 过去式、缺少 type
feat: Added context limit.                  # 非祈使式、首字母大写、句号
fix(opencode): context                      # 没有说明结果
fix: resolve issue #123                     # Issue 引用不应放在标题
WIP: model updates                          # 临时提交不得进入共享历史
```

### 正文

正文说明 **为什么** 需要修改、此前有什么问题、采用何种关键做法，以及用户、配置或兼容性会受到什么影响；不要逐行复述 diff。正文同样使用英文，采用完整句子和正常标点。必要时记录被否决方案及原因，使未来维护者无需依赖外部讨论也能理解取舍。

一个提交只表达一个可独立理解和回退的逻辑目的。功能及其测试、修复及其回归测试、源码及其同步生成的 `switch-model.sh` 应位于同一提交；无关格式化、重命名、依赖升级和重构必须拆分。共享分支和 Pull Request 中不得保留 `fixup!`、`squash!` 或无法通过测试的中间提交。

```text
fix(opencode): normalize context limits before model generation

Values supplied with --context were forwarded without one canonical form,
which made equivalent limits produce inconsistent generated model entries.
Normalize the accepted input before generation so preview and write modes use
the same limit while preserving the original model window.
```

### 页脚、Issue 与兼容性

footer 使用 Git trailer 形式：`Token: value`，并与正文以一个空行分隔。仅当引用准确且对读者有帮助时使用以下 trailer：

```text
Fixes #123
Closes #123
Refs #456
```

`Fixes` 和 `Closes` 只用于该提交合入后确实关闭的 Issue；相关但不会关闭的工作使用 `Refs`。不添加虚假的 `Reviewed-by:`、`Tested-by:`、`Signed-off-by:`、`Co-authored-by:` 或 AI 相关 trailer。

改变已发布命令、参数、配置格式、默认行为或 Host 行为时，必须在标题的 `type` 或 `scope` 后添加 `!`，并添加大写的 `BREAKING CHANGE:` footer，明确旧行为、影响范围和可执行的迁移方式：

```text
feat(opencode)!: remove deprecated limit option

The --limit alias duplicates the context submode and produces an ambiguous
configuration surface. Keep --context as the single supported option.

BREAKING CHANGE: `--limit` is no longer accepted. Replace it with
`--context <limit>`; accepted values are `200000`, `200,000`, and `200k`.
```

安全问题不在公开提交消息中披露未修复漏洞细节、凭据、个人 Host 或其他敏感信息；遵循 [SECURITY.md](./SECURITY.md) 的披露流程。

## Pull Request

- 一个 Pull Request 聚焦一个主题，并在请求审查前自行检查 diff。
- 标题使用上述提交模板。
- 描述简要说明：为什么修改、主要变化、实际验证、兼容性或已知风险。
- 说明影响的 Host 和配置文件；对写入、备份、恢复和 Preview 副作用增加回归测试。
