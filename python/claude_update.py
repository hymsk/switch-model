# -*- coding: utf-8 -*-
"""更新 Claude Code 配置文件"""
import json, os, sys

def main():
    try:
        filepath = os.environ['SWITCH_MODEL_FILE']
        url = os.environ['SWITCH_MODEL_BASE_URL']
        sk = os.environ['SWITCH_MODEL_API_KEY']
        model = os.environ['SWITCH_MODEL_NAME']
        with open(filepath, 'r') as f:
            data = json.load(f)
        data.setdefault('env', {})['ANTHROPIC_BASE_URL'] = url
        data['env']['ANTHROPIC_AUTH_TOKEN'] = sk
        data['model'] = model
        json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write('\n')
        sys.exit(0)
    except Exception as e:
        sys.stderr.write('Error: ' + str(e) + '\n')
        sys.exit(1)

if __name__ == "__main__":
    main()
