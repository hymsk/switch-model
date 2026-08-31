# ==================== 配置区域 ====================
# 所有默认值在此集中配置，便于维护

# Claude Code 配置文件路径
CLAUDE_SETTINGS="$HOME/.claude/settings.json"

# Codex 配置文件路径
CODEX_AUTH="$HOME/.codex/auth.json"
CODEX_CONFIG="$HOME/.codex/config.toml"

# OpenCode 配置文件路径
OPENCODE_CONFIG="$HOME/.config/opencode/opencode.json"

# SK 文件目录
DEFAULT_SK_DIR="$HOME/.config/api-keys"

# SK 文件名（不含路径）
DEFAULT_SK_FILENAME="default.sk"

# API 提供商 URL；公开版本不连接任何预设服务。
DEFAULT_API_URL="${SWITCH_MODEL_BASE_URL:-}"

# Claude 默认模型
DEFAULT_CLAUDE_MODEL="opus"

# Codex 默认模型
DEFAULT_CODEX_MODEL="gpt-5.5"

# OpenCode 默认 provider ID
DEFAULT_OPENCODE_PROVIDER="newapi"

# OpenCode 默认 provider 名称
DEFAULT_OPENCODE_PROVIDER_NAME="New API"

# OpenCode 上下文子模式列表（逗号分隔，0 表示不生成子模式）
# 超过指定值的模型会保留原版本，并为每个适用值生成限制版本
DEFAULT_CONTEXT="258000"

# OpenCode 模型显式映射文件；存在时优先于 catalog 匹配与前缀回退
DEFAULT_OPENCODE_MAPPING_FILE="$HOME/.config/api-keys/model-mapping.json"

# OpenCode 同步报告位置；仅实际写入时覆盖最新报告以便审计
DEFAULT_OPENCODE_REPORT_FILE="${XDG_STATE_HOME:-$HOME/.local/state}/opencode/switch-model-report.json"
