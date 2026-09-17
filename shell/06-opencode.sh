# ==================== OpenCode 配置 ====================

run_opencode_sync() {
    if ! declare -F python_sync_new_api_opencode >/dev/null; then
        echo -e "${RED}Error: embedded OpenCode sync helper is unavailable${NC}" >&2
        echo -e "${YELLOW}请运行 bash build.sh 重新生成 switch-model.sh${NC}" >&2
        return 1
    fi

    python_sync_new_api_opencode "$@"
}

# 更新 OpenCode 配置文件（调用 sync_new_api_opencode.py）
# 参数: $1=base_url, $2=provider, $3=provider_name, $4=context
update_opencode_config() {
    local base_url="$1"
    local provider="${2:-$DEFAULT_OPENCODE_PROVIDER}"
    local provider_name="${3:-$DEFAULT_OPENCODE_PROVIDER_NAME}"
    local context="${4-$DEFAULT_CONTEXT}"
    local mapping_file="${OPENCODE_MAPPING_FILE:-$DEFAULT_OPENCODE_MAPPING_FILE}"
    local mapping_file_explicit="${OPENCODE_MAPPING_FILE_EXPLICIT:-false}"
    local prefix_fallback="${OPENCODE_PREFIX_FALLBACK:-true}"
    local catalog_refresh="${OPENCODE_CATALOG_REFRESH:-true}"
    local report_file="${OPENCODE_REPORT_FILE:-$DEFAULT_OPENCODE_REPORT_FILE}"
    local -a sync_args=()

    if [ -f "$mapping_file" ]; then
        sync_args+=(--mapping-file "$mapping_file")
    elif [ "$mapping_file_explicit" = true ]; then
        echo -e "${RED}Error: 指定的映射文件不存在: $mapping_file${NC}" >&2
        return 1
    fi
    if [ "$prefix_fallback" = false ]; then
        sync_args+=(--no-prefix-fallback)
    fi
    if [ "$catalog_refresh" = false ]; then
        sync_args+=(--no-catalog-refresh)
    fi
    if [ "${INSECURE:-false}" = true ]; then
        sync_args+=(--insecure)
    fi

    mkdir -p "$(dirname "$report_file")"

    if [ ! -f "$OPENCODE_CONFIG" ]; then
        echo -e "${YELLOW}OpenCode config 文件不存在，将创建新文件${NC}"
        mkdir -p "$(dirname "$OPENCODE_CONFIG")"
    fi

    # 读取 sk 从环境变量传递
    local api_key
    api_key=$(cat "$SK_FILE" | tr -d '[:space:]')

    # 调用内嵌同步器直接生成并写入配置（apiKey 引用由 --api-key-file 生成）
    if NEWAPI_API_KEY="$api_key" \
    NEWAPI_BASE_URL="$base_url" \
        run_opencode_sync \
        --provider "$provider" \
        --provider-name "$provider_name" \
        --catalog-mode all \
        --api-key-file "$SK_FILE" \
        --config "$OPENCODE_CONFIG" \
        --write \
        --report "$report_file" \
        --context "$context" \
        "${sync_args[@]}" \
        2>&1; then
        echo -e "${GREEN}OpenCode config 更新成功${NC}"
        return 0
    else
        echo -e "${RED}OpenCode config 更新失败${NC}"
        return 1
    fi
}

# 预览 OpenCode 配置（调用 sync_new_api_opencode.py 生成预览）
# 参数: $1=base_url, $2=provider, $3=provider_name, $4=context
preview_opencode_config() {
    local base_url="$1"
    local provider="${2:-$DEFAULT_OPENCODE_PROVIDER}"
    local provider_name="${3:-$DEFAULT_OPENCODE_PROVIDER_NAME}"
    local context="${4-$DEFAULT_CONTEXT}"
    local mapping_file="${OPENCODE_MAPPING_FILE:-$DEFAULT_OPENCODE_MAPPING_FILE}"
    local mapping_file_explicit="${OPENCODE_MAPPING_FILE_EXPLICIT:-false}"
    local prefix_fallback="${OPENCODE_PREFIX_FALLBACK:-true}"
    local catalog_refresh="${OPENCODE_CATALOG_REFRESH:-true}"
    local report_file
    local -a sync_args=()

    if [ -f "$mapping_file" ]; then
        sync_args+=(--mapping-file "$mapping_file")
    elif [ "$mapping_file_explicit" = true ]; then
        echo -e "${RED}Error: 指定的映射文件不存在: $mapping_file${NC}" >&2
        return 1
    fi
    if [ "$prefix_fallback" = false ]; then
        sync_args+=(--no-prefix-fallback)
    fi
    if [ "$catalog_refresh" = false ]; then
        sync_args+=(--no-catalog-refresh)
    fi
    if [ "${INSECURE:-false}" = true ]; then
        sync_args+=(--insecure)
    fi

    echo -e "${BLUE}=== OpenCode 配置预览 ===${NC}"
    echo ""
    echo -e "${YELLOW}配置文件:${NC} $OPENCODE_CONFIG"
    echo ""

    # 读取 sk 从环境变量传递
    local api_key
    api_key=$(cat "$SK_FILE" | tr -d '[:space:]')

    # 预览只使用临时文件，不写持久报告。
    local preview_file
    preview_file=$(mktemp "${TMPDIR:-/tmp}/switch-model-preview.XXXXXX.json") || return 1
    report_file=$(mktemp "${TMPDIR:-/tmp}/switch-model-report.XXXXXX.json") || {
        rm -f "$preview_file"
        return 1
    }

    # 调用内嵌同步器生成预览（apiKey 引用由 --api-key-file 生成）
    local exit_code
    if NEWAPI_API_KEY="$api_key" \
    NEWAPI_BASE_URL="$base_url" \
        run_opencode_sync \
        --provider "$provider" \
        --provider-name "$provider_name" \
        --catalog-mode all \
        --api-key-file "$SK_FILE" \
        --output "$preview_file" \
        --report "$report_file" \
        --context "$context" \
        "${sync_args[@]}" \
        2>&1; then
        exit_code=0
    else
        exit_code=$?
    fi

    if [ $exit_code -eq 0 ] && [ -f "$preview_file" ]; then
        echo -e "${YELLOW}将要写入的内容:${NC}"
        cat "$preview_file"
        echo ""

        # 显示匹配报告摘要
        if [ -f "$report_file" ]; then
            local summary
            local python_cmd
            python_cmd=$(get_python_cmd)
            summary=$("$python_cmd" - "$report_file" 2>/dev/null <<'PYEOF'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as file:
    report = json.load(file)
summary = report.get("summary", {})
print(
    f"matched: {summary.get('matched', 0)}, "
    f"mapped: {summary.get('mapped', 0)}, "
    f"guessed: {summary.get('guessed', 0)}, "
    f"ambiguous: {summary.get('ambiguous', 0)}, "
    f"unmatched: {summary.get('unmatched', 0)}"
)
PYEOF
)
            echo -e "${YELLOW}匹配结果:${NC} $summary"
        fi
    else
        echo -e "${RED}生成预览失败${NC}"
    fi

    # 清理临时文件
    rm -f "$preview_file" "$report_file"

    return $exit_code
}

# OpenCode 模式主函数
# 参数: $1=API_URL, $2=provider, $3=provider_name, $4=context
opencode_main() {
    local api_url="$1"
    local provider="${2:-$DEFAULT_OPENCODE_PROVIDER}"
    local provider_name="${3:-$DEFAULT_OPENCODE_PROVIDER_NAME}"
    local context="${4-$DEFAULT_CONTEXT}"

    # 在创建或更新 OpenCode 配置前先校验 SK，避免空 SK 产生配置改动
    read_sk_from_file

    # 删除尾部的 /
    api_url="${api_url%/}"

    # 预览模式
    if [ "$PREVIEW" = true ]; then
        preview_opencode_config "$api_url" "$provider" "$provider_name" "$context"
        return $?
    fi

    echo -e "${BLUE}更新 OpenCode 配置...${NC}"
    echo -e "  SK 文件    : ${YELLOW}$SK_FILE${NC}"
    echo -e "  Base URL   : ${YELLOW}${api_url}${NC}"
    echo -e "  Provider   : ${YELLOW}${provider}${NC}"
    echo -e "  Config     : ${YELLOW}${OPENCODE_CONFIG}${NC}"

    if [ "$context" != "0" ]; then
        echo -e "  Context子模式: ${YELLOW}${context}${NC}"
    fi

    # 更新配置
    if update_opencode_config "$api_url" "$provider" "$provider_name" "$context"; then
        echo ""
        echo -e "${GREEN}✓ OpenCode 切换成功${NC}"
    else
        exit 1
    fi
}
