# Contributing

## Development

修改 `shell/` 或 `python/` 后重新生成 `switch-model.sh`：

```bash
bash build.sh
```

运行验证：

```bash
bash -n build.sh shell/*.sh switch-model.sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
git diff --check
```

测试必须使用 fixture、临时 `HOME` 和本地 mock server，不得调用真实模型服务或读取开发者配置。

## Pull Requests

- 说明影响的 Host 和配置文件。
- 对写入、备份、恢复和 Preview 副作用增加回归测试。
- 不提交生成缓存、凭据、用户配置或本机绝对路径。
- 修改源码时必须包含同步生成的 `switch-model.sh`。
