# ==================== SK 文件管理 ====================

# 运行时变量
TOOL_MODE=""
SK_DIR="$DEFAULT_SK_DIR"
SK_FILENAME="$DEFAULT_SK_FILENAME"
SK_FILE="$SK_DIR/$SK_FILENAME"
CUSTOM_SK=""

# 确保 api-keys 目录下存在保护文件
ensure_api_keys_protection() {
    local dir="$DEFAULT_SK_DIR"
    local protection_content='# 安全说明

> 此目录下 .sk 文件不允许读取

## .sk 文件格式说明

- 文件扩展名：`.sk`
- 文件内容：纯文本，仅包含 API Key 字符串
- 文件权限：建议设置为 `600`（仅所有者可读写）
- 示例：`printf '%s\n' '<api-key>' > ~/.config/api-keys/default.sk`

## 安全警告

此目录下的 `.sk` 文件包含敏感的 API Key 信息，AI 工具不应读取或输出这些文件的内容。'

    # 创建目录（如果不存在）
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        chmod 700 "$dir"
    fi

    # 创建 CLAUDE.md（如果不存在）
    if [ ! -f "$dir/CLAUDE.md" ]; then
        echo "$protection_content" > "$dir/CLAUDE.md"
        chmod 644 "$dir/CLAUDE.md"
    fi

    # 创建 AGENTS.md（如果不存在）
    if [ ! -f "$dir/AGENTS.md" ]; then
        echo "$protection_content" > "$dir/AGENTS.md"
        chmod 644 "$dir/AGENTS.md"
    fi
}

# 从 sk 文件读取 API Key
# 参数: $1 - sk 文件路径（可选，默认使用 SK_FILE）
read_sk_from_file() {
    local file="${1:-$SK_FILE}"
    if [ ! -f "$file" ]; then
        echo -e "${RED}Error: SK 文件不存在: $file${NC}" >&2
        exit 1
    fi
    if [ ! -r "$file" ]; then
        echo -e "${RED}Error: SK 文件不可读: $file${NC}" >&2
        exit 1
    fi
    CUSTOM_SK=$(cat "$file" | tr -d '[:space:]')
    if [ -z "$CUSTOM_SK" ]; then
        echo -e "${YELLOW}SK 文件为空: $file${NC}" >&2
        echo -e "${YELLOW}请写入 API Key 后再运行；未执行模型切换。${NC}" >&2
        exit 0
    fi
    if [ "$PREVIEW" != true ]; then
        ensure_api_keys_protection
    fi
}
