# ==================== Claude Code 配置 ====================

# 更新 Claude Code 配置文件
# 参数: $1=文件路径, $2=API_URL, $3=sk, $4=model
update_claude_config() {
    local file="$1"
    local url="$2"
    local sk="$3"
    local model="$4"

    # 凭据通过子进程环境传递，避免暴露在进程参数中。
    SWITCH_MODEL_FILE="$file" SWITCH_MODEL_BASE_URL="$url" \
        SWITCH_MODEL_API_KEY="$sk" SWITCH_MODEL_NAME="$model" \
        python_claude_update
}

# 预览 Claude Code 配置
# 参数: $1=API_URL, $2=sk, $3=model, $4=model_list
preview_claude_config() {
    local url="$1"
    local sk="$2"
    local model="$3"
    local model_list="$4"

    echo -e "${BLUE}=== Claude Code 配置预览 ===${NC}"
    echo ""
    echo -e "${YELLOW}配置文件:${NC} $CLAUDE_SETTINGS"
    echo ""

    # 显示可用模型列表
    if [ -n "$model_list" ]; then
        echo -e "${YELLOW}可用模型列表:${NC}"
        local models=()
        IFS=$'\n' read -d '' -ra models <<< "$model_list" || true
        local i
        for i in "${!models[@]}"; do
            if [ "${models[$i]}" = "$model" ]; then
                echo -e "  $((i+1))) ${GREEN}${models[$i]} (已选择)${NC}"
            else
                echo "  $((i+1))) ${models[$i]}"
            fi
        done
        echo ""
    fi

    echo -e "${YELLOW}已选择模型:${NC} $model"
    echo ""
    echo -e "${YELLOW}将要写入的内容:${NC}"
    echo "{"
    echo '  "env": {'
    echo "    \"ANTHROPIC_BASE_URL\": \"$url\","
    echo '    "ANTHROPIC_AUTH_TOKEN": "<redacted>"'
    echo "  },"
    echo "  \"model\": \"$model\""
    echo "}"
    echo ""
    echo -e "${YELLOW}SK 文件:${NC} $SK_FILE"
    echo -e "${YELLOW}API URL:${NC} $url"
}

# Claude 模式主函数
# 参数: $1=API_URL, $2=auto_model
claude_main() {
    local api_url="$1"
    local auto_model="$2"

    # 读取 sk
    read_sk_from_file
    local sk="$CUSTOM_SK"

    # 删除尾部的 /
    api_url="${api_url%/}"

    # 获取模型列表
    echo -e "${BLUE}正在从 API 获取可用模型列表...${NC}"
    local model_list
    if ! model_list=$(fetch_models "$api_url" "$sk"); then
        echo -e "${RED}Error: 无法从模型服务读取模型列表${NC}" >&2
        return 1
    fi

    # 选择模型
    local model
    if [ -n "$auto_model" ] && [ -n "$model_list" ]; then
        # 自动匹配模型
        local models=()
        IFS=$'\n' read -d '' -ra models <<< "$model_list" || true
        local matched_models=()
        local m
        for m in "${models[@]}"; do
            if [[ "$m" == *"$auto_model"* ]]; then
                matched_models+=("$m")
            fi
        done
        if [ ${#matched_models[@]} -gt 0 ]; then
            model="${matched_models[0]}"
            echo -e "${GREEN}已自动匹配模型: ${YELLOW}$model${NC}"
        else
            model="${models[0]}"
            echo -e "${YELLOW}未匹配到模型 $auto_model，自动选择第一个: ${YELLOW}$model${NC}"
        fi
    elif [ -n "$model_list" ]; then
        # preview 模式或非交互模式下自动选择第一个
        if [ "$PREVIEW" = true ] || [ ! -t 0 ]; then
            local models=()
            IFS=$'\n' read -d '' -ra models <<< "$model_list" || true
            model="${models[0]}"
            echo -e "${GREEN}已自动选择模型: ${YELLOW}$model${NC}"
        else
            # 交互模式
            select_model "$api_url" "$sk" "$auto_model" "$DEFAULT_CLAUDE_MODEL"
            model="$SELECTED_MODEL"
        fi
    else
        echo -e "${RED}Error: 模型服务没有返回可用模型${NC}" >&2
        return 1
    fi

    # 预览模式
    if [ "$PREVIEW" = true ]; then
        preview_claude_config "$api_url" "$sk" "$model" "$model_list"
        return 0
    fi

    # 检查配置文件
    if [ ! -f "$CLAUDE_SETTINGS" ]; then
        echo -e "${RED}Error: $CLAUDE_SETTINGS not found${NC}"
        exit 1
    fi

    # 备份配置文件
    local backup="${CLAUDE_SETTINGS}.bak.$(date +%Y%m%d%H%M%S)"
    cp "$CLAUDE_SETTINGS" "$backup"
    echo -e "${GREEN}Backup saved to: $backup${NC}"

    # 更新配置文件
    if update_claude_config "$CLAUDE_SETTINGS" "$api_url" "$sk" "$model" > "${CLAUDE_SETTINGS}.tmp" 2>/dev/null; then
        mv "${CLAUDE_SETTINGS}.tmp" "$CLAUDE_SETTINGS"

        echo ""
        echo -e "${GREEN}✓ Claude 切换成功${NC}"
        echo -e "  SK 文件    : ${YELLOW}$SK_FILE${NC}"
        echo -e "  BASE_URL   : ${YELLOW}$api_url${NC}"
        echo -e "  MODEL      : ${YELLOW}$model${NC}"
    else
        echo -e "${RED}Error: failed to update settings, restoring backup...${NC}"
        rm -f "${CLAUDE_SETTINGS}.tmp"
        cp "$backup" "$CLAUDE_SETTINGS"
        exit 1
    fi
}
