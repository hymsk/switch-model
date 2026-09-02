# Switch Model Repository Rules

本仓库只维护 `switch-model`。默认使用中文沟通；代码、命令、路径和 API 名称保留原文。

## 不变量

- `shell/` 和 `python/` 是源码，`switch-model.sh` 是 `build.sh` 生成的单文件分发产物。
- 修改源码后必须运行 `bash build.sh`，并验证生成物与源码一致。
- 构建只使用显式的 `OPENCODE_MODELS_FILE`，或复用 Git `HEAD` 生成物中的已审计 catalog；不得信任 dirty 生成物，也不得隐式读取或刷新开发机模型 cache。
- 不在输出、日志、预览、测试或文档中显示 API Key 或其前缀。
- 不记录个人服务地址、个人邮箱、token、cookie、私钥或真实 Host 配置。
- 公开基线从 `v0.1.0rc1` 开始维护向后兼容；此前的内部布局不属于兼容范围。

## 验证

```bash
bash -n build.sh shell/*.sh switch-model.sh
bash build.sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
git diff --check
```
