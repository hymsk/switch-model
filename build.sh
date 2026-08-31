#!/bin/bash
# 合并所有模块为一个脚本
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT="$SCRIPT_DIR/switch-model.sh"
BUILD_OUTPUT="$(mktemp "$SCRIPT_DIR/.switch-model.sh.XXXXXX")"
SHELL_DIR="$SCRIPT_DIR/shell"
PYTHON_DIR="$SCRIPT_DIR/python"
OPENCODE_MODELS_FILE="${OPENCODE_MODELS_FILE:-$SCRIPT_DIR/tests/fixtures/opencode-models.json}"

cleanup_build_output() {
    rm -f "$BUILD_OUTPUT"
}

trap cleanup_build_output EXIT

validate_opencode_models_file() {
    python3 - "$1" >/dev/null <<'PYEOF'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
providers = payload.get("providers") if isinstance(payload, dict) else None
if not isinstance(providers, dict):
    providers = payload
if not isinstance(providers, dict):
    raise SystemExit("catalog must be a provider object")

entry_count = 0
for provider_id, provider in providers.items():
    if not str(provider_id).strip():
        continue
    if not isinstance(provider, dict):
        continue
    models = provider.get("models")
    if not isinstance(models, dict):
        continue
    for configured_id, raw_model in models.items():
        if not isinstance(raw_model, dict):
            continue
        model_id = str(raw_model.get("id") or configured_id).strip()
        if not model_id:
            continue
        entry_count += 1

if entry_count == 0:
    raise SystemExit("catalog contains no usable models")
PYEOF
}

ensure_opencode_models_file() {
    if [ -r "$OPENCODE_MODELS_FILE" ] && validate_opencode_models_file "$OPENCODE_MODELS_FILE"; then
        echo "Using OpenCode catalog: $OPENCODE_MODELS_FILE"
        return 0
    fi

    echo "Error: OpenCode catalog is missing or invalid: $OPENCODE_MODELS_FILE" >&2
    echo "Set OPENCODE_MODELS_FILE to a reviewed catalog snapshot before building." >&2
    return 1
}

validate_embedded_opencode_catalog() {
    local generated_file="${1:-$OUTPUT}"
    python3 - "$generated_file" >/dev/null <<'PYEOF'
import base64
import gzip
import json
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
match = re.search(r"^EMBEDDED_OPENCODE_MODELS_GZIP = '([^']+)'$", text, re.MULTILINE)
if not match or not match.group(1):
    raise SystemExit("embedded OpenCode catalog is empty")

payload = json.loads(gzip.decompress(base64.b64decode(match.group(1))).decode("utf-8"))
providers = payload.get("providers") if isinstance(payload, dict) else None
if not isinstance(providers, dict):
    providers = payload
if not isinstance(providers, dict):
    raise SystemExit("embedded OpenCode catalog must be a provider object")

entry_count = 0
for provider_id, provider in providers.items():
    if not str(provider_id).strip():
        continue
    if not isinstance(provider, dict):
        continue
    models = provider.get("models")
    if isinstance(models, dict):
        for configured_id, raw_model in models.items():
            if not isinstance(raw_model, dict):
                continue
            model_id = str(raw_model.get("id") or configured_id).strip()
            if not model_id:
                continue
            entry_count += 1
if entry_count == 0:
    raise SystemExit("embedded OpenCode catalog contains no usable models")
PYEOF
}

append_embedded_opencode_catalog() {
    python3 - "$OPENCODE_MODELS_FILE" >> "$BUILD_OUTPUT" <<'PYEOF'
import base64
import gzip
import sys
from pathlib import Path

catalog = Path(sys.argv[1]).read_bytes()
encoded = base64.b64encode(gzip.compress(catalog, mtime=0)).decode("ascii")
print("EMBEDDED_OPENCODE_MODELS_GZIP = " + repr(encoded))
PYEOF
}

echo "Building switch-model.sh..."
ensure_opencode_models_file

# 生成脚本头部
cat > "$BUILD_OUTPUT" << 'HEADER'
#!/bin/bash
# Auto-generated file. Do not edit manually.
# Run bash build.sh to regenerate.
#
# Switch Model - 模型切换脚本
#
# 功能说明：
#   - 从 sk 文件读取 API Key，自动写入 Claude Code / Codex / OpenCode 配置文件
#   - 支持 Claude Code、Codex、OpenCode 三种工具模式
#   - 自动从 API 获取可用模型列表并选择
#   - 自动创建 ~/.config/api-keys/ 目录及保护文件
#
# 支持平台: Linux / macOS / Windows (Git Bash / WSL)
# 运行依赖: Python 3、curl
#
# 使用方法:
#   bash switch-model.sh <claude|codex|opencode> <url> [model] [--sk-filename <name>] [--sk-file <path>]
#
# 示例:
#   bash switch-model.sh claude https://api.example.com
#   bash switch-model.sh codex https://api.example.com --sk-filename work.sk
#   bash switch-model.sh opencode https://api.example.com --preview

set -euo pipefail
umask 077

HEADER

# 嵌入 Python 脚本
cat >> "$BUILD_OUTPUT" << 'PYTHON_SECTION'
# ==================== 嵌入的 Python 脚本 ====================
# 以下 Python 代码由 build.sh 从 python/ 目录嵌入

PYTHON_SECTION

# 嵌入每个 Python 脚本为 shell 函数
for py_file in "$PYTHON_DIR"/*.py; do
    if [ -f "$py_file" ]; then
        func_name="python_$(basename "$py_file" .py)"
        echo "" >> "$BUILD_OUTPUT"
        echo "# Python 脚本: $(basename "$py_file")" >> "$BUILD_OUTPUT"
        echo "${func_name}() {" >> "$BUILD_OUTPUT"
        echo '    local python_cmd=$(get_python_cmd)' >> "$BUILD_OUTPUT"
        echo '    "$python_cmd" - "$@" << '"'"'PYEOF'"'"'' >> "$BUILD_OUTPUT"
        if [ "$(basename "$py_file")" = "sync_new_api_opencode.py" ]; then
            while IFS= read -r line || [ -n "$line" ]; do
                printf '%s\n' "$line" >> "$BUILD_OUTPUT"
                if [ "$line" = "from __future__ import annotations" ]; then
                    append_embedded_opencode_catalog
                fi
            done < "$py_file"
        else
            cat "$py_file" >> "$BUILD_OUTPUT"
        fi
        echo "" >> "$BUILD_OUTPUT"
echo 'PYEOF' >> "$BUILD_OUTPUT"
        echo "}" >> "$BUILD_OUTPUT"
    fi
done

# 合并 shell 模块文件
for module in "$SHELL_DIR"/[0-9]*.sh; do
    if [ -f "$module" ]; then
        echo "" >> "$BUILD_OUTPUT"
        echo "# === $(basename "$module") ===" >> "$BUILD_OUTPUT"
        cat "$module" >> "$BUILD_OUTPUT"
    fi
done

# 添加脚本尾部
cat >> "$BUILD_OUTPUT" << 'FOOTER'

# === End of auto-generated file ===
FOOTER

validate_embedded_opencode_catalog "$BUILD_OUTPUT"

chmod 755 "$BUILD_OUTPUT"
mv -f "$BUILD_OUTPUT" "$OUTPUT"
trap - EXIT

echo "Generated: $OUTPUT"
echo "Total lines: $(wc -l < "$OUTPUT")"
