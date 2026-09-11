# -*- coding: utf-8 -*-
"""更新 Codex 配置文件"""
import os, sys, tempfile

def write_bytes_atomically(filepath, content):
    """原子写入文件"""
    directory = os.path.dirname(filepath)
    fd, temporary = tempfile.mkstemp(prefix='.config.', dir=directory)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, filepath)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise

def main():
    try:
        url, model, filepath = sys.argv[1], sys.argv[2], sys.argv[3]

        # 确保目录存在
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        # 如果文件不存在，创建默认配置（使用 LF 换行符）
        if not os.path.exists(filepath):
            default_config = 'model_provider = "MyProvider"\n'
            default_config += 'model = "{model}"\n'
            default_config += 'model_reasoning_effort = "high"\n'
            default_config += 'disable_response_storage = true\n'
            default_config += 'personality = "pragmatic"\n'
            default_config += '\n'
            default_config += '[model_providers.MyProvider]\n'
            default_config += 'name = "MyProvider"\n'
            default_config += 'base_url = "{url}/v1"\n'
            default_config += 'wire_api = "responses"\n'
            default_config += 'requires_openai_auth = true\n'
            default_config = default_config.format(model=model, url=url)
            write_bytes_atomically(filepath, default_config.encode('utf-8'))
            print('Created: model={0}, base_url={1}'.format(model, url))
            sys.exit(0)

        # 读取现有配置（统一换行符为 LF）
        with open(filepath, 'rb') as f:
            raw = f.read()
        # 将 CRLF 和 CR 统一为 LF
        content = raw.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
        lines = content.decode('utf-8').split('\n')

        # 更新配置
        new_lines = []
        in_myprovider_section = False
        model_provider_updated = False
        model_updated = False
        base_url_updated = False

        for line in lines:
            stripped = line.strip()

            # 更新 model_provider 行
            if stripped.startswith('model_provider = ') and not model_provider_updated:
                new_lines.append('model_provider = "MyProvider"')
                model_provider_updated = True
                continue

            # 更新 model 行
            if stripped.startswith('model = ') and not model_updated:
                new_lines.append('model = "{0}"'.format(model))
                model_updated = True
                continue

            # 进入 MyProvider section
            if stripped.startswith('[model_providers.MyProvider]'):
                in_myprovider_section = True
                new_lines.append(line)
                continue

            # 在 MyProvider section 中更新 base_url
            if in_myprovider_section and stripped.startswith('base_url = ') and not base_url_updated:
                new_lines.append('base_url = "{0}/v1"'.format(url))
                base_url_updated = True
                continue

            # 离开 MyProvider section
            if in_myprovider_section and stripped.startswith('[') and not stripped.startswith('[model_providers.MyProvider]'):
                in_myprovider_section = False

            new_lines.append(line)

        if not model_provider_updated:
            new_lines.insert(0, 'model_provider = "MyProvider"')
        if not model_updated:
            insert_at = 1 if new_lines and new_lines[0].startswith('model_provider = ') else 0
            new_lines.insert(insert_at, 'model = "{0}"'.format(model))
        if not base_url_updated:
            if new_lines and new_lines[-1] != '':
                new_lines.append('')
            if not any(line.strip() == '[model_providers.MyProvider]' for line in new_lines):
                new_lines.extend([
                    '[model_providers.MyProvider]',
                    'name = "MyProvider"',
                    'base_url = "{0}/v1"'.format(url),
                    'wire_api = "responses"',
                    'requires_openai_auth = true',
                ])
            else:
                section_index = next(
                    index
                    for index, line in enumerate(new_lines)
                    if line.strip() == '[model_providers.MyProvider]'
                )
                new_lines.insert(section_index + 1, 'base_url = "{0}/v1"'.format(url))

        # 写回文件，使用 LF 换行符（TOML 标准）
        write_bytes_atomically(filepath, '\n'.join(new_lines).encode('utf-8'))

        print('Updated: model={0}, base_url={1}'.format(model, url))
        sys.exit(0)
    except Exception as e:
        sys.stderr.write('Error: ' + str(e) + '\n')
        sys.exit(1)

if __name__ == "__main__":
    main()
