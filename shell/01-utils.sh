# ==================== 工具函数 ====================

# 颜色定义（仅 TTY 下启用颜色，管道/重定向时无色，避免污染输出）
if [ -t 1 ] && [ -t 2 ]; then
    RED='\033[31m'
    GREEN='\033[32m'
    YELLOW='\033[33m'
    BLUE='\033[34m'
    NC='\033[0m'
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    NC=''
fi

# 获取可用的 Python 3 命令名
get_python_cmd() {
    local candidate

    if command -v uv >/dev/null 2>&1; then
        candidate=$(uv python find 2>/dev/null | tr -d '\r')
        if [ -n "$candidate" ]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    fi

    if command -v python3 &>/dev/null; then
        echo "python3"
    elif command -v python &>/dev/null && python -c "import sys; raise SystemExit(0 if sys.version_info[0] >= 3 else 1)" 2>/dev/null; then
        echo "python"
    fi
}

# 检查 Python 3 与 json 模块是否可用
check_json_tool() {
    local python_cmd=$(get_python_cmd)
    if [ -z "$python_cmd" ]; then
        echo -e "${RED}错误: 未找到 Python 3${NC}" >&2
        return 1
    fi
    "$python_cmd" -c "import json; import sys" 2>/dev/null || {
        echo -e "${RED}错误: 无法找到可用的 Python 3 与 json 模块${NC}" >&2
        return 1
    }
    return 0
}
