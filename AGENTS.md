# Switch Model Repository Rules

本仓库只维护 `switch-model`。默认使用中文沟通；代码、命令、路径和 API 名称保留原文。

## 不变量

- `shell/` 和 `python/` 是源码，`switch-model.sh` 是 `build.sh` 生成的单文件分发产物。
- 修改源码后必须运行 `bash build.sh`，并验证生成物与源码一致。
- 构建只使用显式的 `OPENCODE_MODELS_FILE`，或在隔离的临时 `XDG_CACHE_HOME` 中先刷新 catalog 再嵌入；不得信任 dirty 生成物，也不得读取或改写开发机自身的模型 cache。
- 默认构建的 catalog 刷新失败必须让构建失败，不得静默回退到旧 catalog。
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
