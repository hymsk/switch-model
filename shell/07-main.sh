# ==================== 使用帮助 ====================

usage() {
    local exit_code="${1:-1}"
    echo "Usage: $0 <claude|codex|opencode> <url> [model] [--sk-filename <name>] [--sk-file <path>] [--preview]"
    echo ""
    echo "Arguments:"
    echo "  <claude|codex|opencode> 工具模式（必需，作为第一个参数）"
    echo "  url                     OpenAI-compatible 模型服务 URL；也可设置 SWITCH_MODEL_BASE_URL"
    echo "  model                   模型名，自动 grep 选择"
    echo "                          - Claude 默认: $DEFAULT_CLAUDE_MODEL"
    echo "                          - Codex 默认: $DEFAULT_CODEX_MODEL"
    echo "                          - OpenCode: 不需要指定"
    echo ""
    echo "Options:"
    echo "  --sk-filename <name>    指定 SK 文件名（默认: $DEFAULT_SK_FILENAME）"
    echo "  --sk-file <path>        指定 SK 文件完整路径（优先级高于 --sk-filename）"
    echo "  --preview               预览模式，只输出配置文件位置与内容，不实际写入"
    echo ""
    echo "OpenCode Options:"
    echo "  --context <tokens[,tokens...]>  为超过指定值的模型生成上下文子模式（默认: $DEFAULT_CONTEXT；0 表示禁用）"
    echo "  --mapping-file <path>            显式模型 ID 到 OpenCode catalog ID 的 JSON 映射（默认: $DEFAULT_OPENCODE_MAPPING_FILE）"
    echo "  --no-prefix-fallback             关闭仅在精确匹配失败后启用的安全前缀元数据回退"
    echo "  --replace-providers              确认写入时替换 OpenCode 配置中的整个 provider 对象"
    echo "  Catalog 运行时顺序: 本地 cache -> 内嵌完整 snapshot -> 实时查询"
    echo "  实时查询命令: opencode models --verbose --pure"
    echo "  构建时使用受审计的 OPENCODE_MODELS_FILE；不会隐式刷新本机 cache"
    echo ""
    echo "Examples:"
    echo "  # Claude 模式"
    echo "  $0 claude https://api.example.com $DEFAULT_CLAUDE_MODEL"
    echo "  $0 claude https://api.example.com --sk-filename work.sk"
    echo ""
    echo "  # Codex 模式"
    echo "  $0 codex https://api.example.com"
    echo "  $0 codex https://api.example.com --sk-filename work.sk"
    echo ""
    echo "  # OpenCode 模式"
    echo "  $0 opencode https://api.example.com --preview"
    echo "  $0 opencode https://api.example.com --replace-providers"
    echo "  $0 opencode https://api.example.com --context 128000 --replace-providers"
    echo "  $0 opencode https://api.example.com --mapping-file ~/.config/api-keys/model-mapping.json --replace-providers"
    echo "  $0 opencode https://api.example.com --no-prefix-fallback --replace-providers"
    echo ""
    echo "  # 预览模式"
    echo "  $0 claude https://api.example.com --preview"
    echo "  $0 codex https://api.example.com --preview"
    echo "  $0 opencode https://api.example.com --preview"
    exit "$exit_code"
}

validate_context_argument() {
    local value="$1"
    if ! [[ "$value" =~ ^[[:space:]]*[0-9]+[[:space:]]*(,[[:space:]]*[0-9]+[[:space:]]*)*$ ]]; then
        echo -e "${RED}Error: --context must be a comma-separated list of non-negative integers${NC}" >&2
        return 1
    fi

    local compact="${value//[[:space:]]/}"
    local item
    local has_zero=false
    local has_positive=false
    local -a values=()
    IFS=',' read -ra values <<< "$compact"
    for item in "${values[@]}"; do
        if [[ "$item" =~ ^0+$ ]]; then
            has_zero=true
        else
            has_positive=true
        fi
    done
    if [ "$has_zero" = true ] && [ "$has_positive" = true ]; then
        echo -e "${RED}Error: --context value 0 cannot be combined with other context values${NC}" >&2
        return 1
    fi
}

# ==================== 主逻辑 ====================

# 预览模式标志
PREVIEW=false
OPENCODE_MAPPING_FILE="$DEFAULT_OPENCODE_MAPPING_FILE"
OPENCODE_MAPPING_FILE_EXPLICIT=false
OPENCODE_PREFIX_FALLBACK=true
OPENCODE_REPLACE_PROVIDERS=false

# 检查是否有参数
if [ "$#" -eq 0 ]; then
    echo -e "${RED}Error: 需要指定工具模式 <claude|codex|opencode>${NC}" >&2
    usage
fi

# 第一个参数必须是工具模式或 -h/--help
case "$1" in
    -h|--help)
        usage 0
        ;;
    claude|codex|opencode)
        TOOL_MODE="$1"
        shift
        ;;
    *)
        echo -e "${RED}Error: 第一个参数必须是 'claude'、'codex' 或 'opencode'${NC}" >&2
        usage
        ;;
esac

# 解析剩余选项：扫描所有参数，识别 --* 选项，其余作为位置参数保留
POSITIONAL=()
CONTEXT=$DEFAULT_CONTEXT
while [ "$#" -gt 0 ]; do
    case "$1" in
        -h|--help)
            usage 0
            ;;
        --sk-filename)
            if [ -z "${2:-}" ]; then
                echo -e "${RED}Error: --sk-filename requires argument <name>${NC}"
                usage
            fi
            SK_FILENAME="$2"
            SK_FILE="$SK_DIR/$SK_FILENAME"
            shift 2
            ;;
        --sk-file)
            if [ -z "${2:-}" ]; then
                echo -e "${RED}Error: --sk-file requires argument <path>${NC}"
                usage
            fi
            SK_FILE="$2"
            shift 2
            ;;
        --context)
            if [ -z "${2:-}" ] || [[ "$2" == --* ]]; then
                echo -e "${RED}Error: --context requires argument <tokens[,tokens...]>${NC}"
                usage
            fi
            if ! validate_context_argument "$2"; then
                usage
            fi
            CONTEXT="$2"
            shift 2
            ;;
        --mapping-file)
            if [ -z "${2:-}" ] || [[ "$2" == --* ]]; then
                echo -e "${RED}Error: --mapping-file requires argument <path>${NC}"
                usage
            fi
            OPENCODE_MAPPING_FILE="$2"
            OPENCODE_MAPPING_FILE_EXPLICIT=true
            shift 2
            ;;
        --no-prefix-fallback)
            OPENCODE_PREFIX_FALLBACK=false
            shift
            ;;
        --replace-providers)
            OPENCODE_REPLACE_PROVIDERS=true
            shift
            ;;
        --preview)
            PREVIEW=true
            shift
            ;;
        --*)
            echo -e "${RED}Error: 未知选项 $1${NC}" >&2
            usage
            ;;
        *)
            POSITIONAL+=("$1")
            shift
            ;;
    esac
done
set -- "${POSITIONAL[@]}"

if [ -z "${1:-$DEFAULT_API_URL}" ]; then
    echo -e "${RED}Error: 必须提供模型服务 URL，或设置 SWITCH_MODEL_BASE_URL${NC}" >&2
    usage
fi

# 检查 JSON 处理工具
if ! check_json_tool; then
    exit 1
fi

# 根据工具模式执行
case "$TOOL_MODE" in
    claude)
        URL="${1:-$DEFAULT_API_URL}"
        AUTO_MODEL="${2:-}"
        claude_main "$URL" "$AUTO_MODEL"
        ;;
    codex)
        URL="${1:-$DEFAULT_API_URL}"
        AUTO_MODEL="${2:-}"
        codex_main "$URL" "$AUTO_MODEL"
        ;;
    opencode)
        URL="${1:-$DEFAULT_API_URL}"
        PROVIDER="${2:-$DEFAULT_OPENCODE_PROVIDER}"
        PROVIDER_NAME="${3:-$DEFAULT_OPENCODE_PROVIDER_NAME}"
        opencode_main "$URL" "$PROVIDER" "$PROVIDER_NAME" "$CONTEXT"
        ;;
esac
