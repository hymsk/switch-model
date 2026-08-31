# -*- coding: utf-8 -*-
"""更新 Codex 认证文件"""
import json, os, sys, tempfile

def main():
    try:
        sk = os.environ['SWITCH_MODEL_API_KEY']
        filepath = os.environ['SWITCH_MODEL_AUTH_PATH']

        # 确保目录存在
        directory = os.path.dirname(filepath)
        if not os.path.isdir(directory):
            os.makedirs(directory)

        data = {
            "auth_mode": "apikey",
            "OPENAI_API_KEY": sk
        }
        fd, temporary = tempfile.mkstemp(prefix='.auth.', dir=directory)
        try:
            with os.fdopen(fd, 'w') as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.write('\n')
            os.chmod(temporary, 0o600)
            os.replace(temporary, filepath)
            os.chmod(filepath, 0o600)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
        print('Codex auth updated: {0}'.format(filepath))
        sys.exit(0)
    except Exception as e:
        sys.stderr.write('Error: ' + str(e) + '\n')
        sys.exit(1)

if __name__ == "__main__":
    main()
