# ==================== 模型列表获取 ====================

# 获取模型列表 URL
# 参数: $1 - API 基础 URL
get_models_url() {
    local api_base="${1%/}"
    echo "${api_base}/v1/models"
}

# 从远端读取模型列表
# 参数: $1 - URL, $2 - API Key
fetch_bearer_json() {
    local url="$1"
    local api_key="$2"

    if ! command -v curl >/dev/null 2>&1; then
        echo "错误: 未找到 curl，无法读取模型列表" >&2
        return 1
    fi

    local header_file
    header_file=$(mktemp "${TMPDIR:-/tmp}/switch-model-header.XXXXXX") || return 1
    trap 'rm -f -- "$header_file"' RETURN
    chmod 600 "$header_file" 2>/dev/null || true
    printf 'Authorization: Bearer %s\n' "$api_key" > "$header_file"
    curl --fail --silent --show-error --location \
        --header "@$header_file" "$url" 2>/dev/null
}

# 获取模型列表
# 参数: $1 - API 基础 URL, $2 - API Key
# 返回: 模型 ID 列表 (每行一个)
fetch_models() {
    local api_base="$1"
    local api_key="$2"
    local models_url=$(get_models_url "$api_base")

    # 默认校验证书；HTTPS 校验失败时停止，不降级为不安全连接。
    local response
    response=$(fetch_bearer_json "$models_url" "$api_key") || return 1

    if [ -z "$response" ]; then
        echo "错误: 模型服务返回空响应" >&2
        return 1
    fi

    # 使用 python 解析 JSON 提取模型 ID 列表
    local python_cmd=$(get_python_cmd)
    echo "$response" | "$python_cmd" -c "
import json, sys
try:
    data = json.load(sys.stdin)
    if 'data' in data:
        for item in data['data']:
            model_id = item.get('id', '')
            if model_id:
                sys.stdout.write(model_id.strip() + '\n')
except Exception:
    pass
" | tr -d '\r'
}

# 从模型列表中选择模型
# 参数: $1 - API 基础 URL, $2 - API Key, $3 - 自动匹配关键字, $4 - 默认模型
# 输出: 通过全局变量 SELECTED_MODEL 返回选中的模型
select_model() {
    local provider_base="$1"
    local sk="$2"
    local auto_model="$3"
    local default_model="$4"
    local model_list=""

    SELECTED_MODEL=""

    echo -e "${BLUE}正在从 API 获取可用模型列表...${NC}"
    if ! model_list=$(fetch_models "$provider_base" "$sk"); then
        echo -e "${RED}Error: 无法从模型服务读取模型列表${NC}" >&2
        return 1
    fi

    if [ -n "$model_list" ]; then
        local models=()
        IFS=$'\n' read -d '' -ra models <<< "$model_list" || true

        if [ -n "$auto_model" ]; then
            echo -e "${BLUE}自动匹配模型: ${YELLOW}$auto_model${NC}"
            local matched_models=()
            local m
            for m in "${models[@]}"; do
                if [[ "$m" == *"$auto_model"* ]]; then
                    matched_models+=("$m")
                fi
            done

            if [ ${#matched_models[@]} -gt 0 ]; then
                SELECTED_MODEL="${matched_models[0]}"
                echo -e "${GREEN}已自动选择模型: ${YELLOW}$SELECTED_MODEL${NC}"
            else
                SELECTED_MODEL="${models[0]}"
                echo -e "${YELLOW}未匹配到模型 $auto_model，自动选择第一个: ${YELLOW}$SELECTED_MODEL${NC}"
            fi
        else
            # preview 模式或非交互模式下自动选择第一个
            if [ "$PREVIEW" = true ] || [ ! -t 0 ]; then
                SELECTED_MODEL="${models[0]}"
                echo -e "${GREEN}已自动选择模型: ${YELLOW}$SELECTED_MODEL${NC}"
            else
                echo ""
                echo -e "${BLUE}请选择模型:${NC}"

                local i
                for i in "${!models[@]}"; do
                    printf "  %d) %s\n" $((i+1)) "${models[$i]}"
                done
                echo ""

                local model_choice
                read -p "请输入选项 [1-${#models[@]}]: " model_choice </dev/tty 2>/dev/null || model_choice="1"

                if [[ "$model_choice" =~ ^[0-9]+$ ]] && \
                   [ "$model_choice" -ge 1 ] && \
                   [ "$model_choice" -le ${#models[@]} ]; then
                    SELECTED_MODEL="${models[$((model_choice-1))]}"
                else
                    SELECTED_MODEL="${models[0]}"
                fi

                echo -e "${GREEN}已选择模型: ${YELLOW}$SELECTED_MODEL${NC}"
            fi
        fi
    else
        echo -e "${RED}Error: 模型服务没有返回可用模型${NC}" >&2
        return 1
    fi

    # 去除模型名中的空白字符（\r, \n, 空格等）
    SELECTED_MODEL=$(echo -n "$SELECTED_MODEL" | tr -d '[:space:]')
}
