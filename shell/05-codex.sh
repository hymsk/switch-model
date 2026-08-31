# ==================== Codex 配置 ====================

# 更新 Codex 认证文件
# 参数: $1=sk
update_codex_auth() {
    local sk="$1"
    local auth_backup=""

    # 备份（如果文件存在）
    if [ -f "$CODEX_AUTH" ]; then
        auth_backup="${CODEX_AUTH}.bak.$(date +%Y%m%d%H%M%S)"
        cp "$CODEX_AUTH" "$auth_backup"
        echo -e "${GREEN}Codex auth 备份已保存: $auth_backup${NC}"
    else
        echo -e "${YELLOW}Codex auth 文件不存在，将创建新文件${NC}"
    fi

    SWITCH_MODEL_API_KEY="$sk" SWITCH_MODEL_AUTH_PATH="$CODEX_AUTH" \
        python_codex_auth

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Codex auth 更新成功${NC}"
        return 0
    else
        echo -e "${RED}Codex auth 更新失败${NC}"
        [ -f "$auth_backup" ] && cp "$auth_backup" "$CODEX_AUTH"
        return 1
    fi
}

# 更新 Codex 配置文件
# 参数: $1=url, $2=model
update_codex_config() {
    local url="$1"
    local model="$2"
    local config_backup=""

    # 备份（如果文件存在）
    if [ -f "$CODEX_CONFIG" ]; then
        config_backup="${CODEX_CONFIG}.bak.$(date +%Y%m%d%H%M%S)"
        cp "$CODEX_CONFIG" "$config_backup"
        echo -e "${GREEN}Codex config 备份已保存: $config_backup${NC}"
    else
        echo -e "${YELLOW}Codex config 文件不存在，将创建新文件${NC}"
    fi

    python_codex_config "$url" "$model" "$CODEX_CONFIG"

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Codex config 更新成功${NC}"
        return 0
    else
        echo -e "${RED}Codex config 更新失败${NC}"
        [ -f "$config_backup" ] && cp "$config_backup" "$CODEX_CONFIG"
        return 1
    fi
}

# 预览 Codex 配置
# 参数: $1=url, $2=sk, $3=model, $4=model_list
preview_codex_config() {
    local url="$1"
    local sk="$2"
    local model="$3"
    local model_list="$4"

    echo -e "${BLUE}=== Codex 配置预览 ===${NC}"
    echo ""
    echo -e "${YELLOW}认证文件:${NC} $CODEX_AUTH"
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
    echo -e "${YELLOW}认证文件将要写入:${NC}"
    echo "{"
    echo '  "auth_mode": "apikey",'
    echo '  "OPENAI_API_KEY": "<redacted>"'
    echo "}"
    echo ""
    echo -e "${YELLOW}配置文件:${NC} $CODEX_CONFIG"
    echo -e "${YELLOW}将要写入的内容:${NC}"
    echo 'model_provider = "newapi"'
    echo "model = \"$model\""
    echo 'model_reasoning_effort = "high"'
    echo 'disable_response_storage = true'
    echo 'personality = "pragmatic"'
    echo ""
    echo "[model_providers.newapi]"
    echo 'name = "NewAPI"'
    echo "base_url = \"$url/v1\""
    echo 'wire_api = "responses"'
    echo 'requires_openai_auth = true'
    echo ""
    echo -e "${YELLOW}SK 文件:${NC} $SK_FILE"
    echo -e "${YELLOW}API URL:${NC} $url"
}

# Codex 模式主函数
# 参数: $1=API_URL, $2=auto_model
codex_main() {
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
            select_model "$api_url" "$sk" "$auto_model" "$DEFAULT_CODEX_MODEL"
            model="$SELECTED_MODEL"
        fi
    else
        echo -e "${RED}Error: 模型服务没有返回可用模型${NC}" >&2
        return 1
    fi

    # 预览模式
    if [ "$PREVIEW" = true ]; then
        preview_codex_config "$api_url" "$sk" "$model" "$model_list"
        return 0
    fi

    echo -e "${BLUE}更新 Codex 配置...${NC}"
    echo -e "  SK 文件    : ${YELLOW}$SK_FILE${NC}"
    echo -e "  Base URL   : ${YELLOW}${api_url}${NC}"
    echo -e "  Model      : ${YELLOW}${model}${NC}"

    # 更新 auth.json
    if ! update_codex_auth "$sk"; then
        exit 1
    fi

    # 更新 config.toml
    if ! update_codex_config "$api_url" "$model"; then
        exit 1
    fi

    echo ""
    echo -e "${GREEN}✓ Codex 切换成功${NC}"
}
