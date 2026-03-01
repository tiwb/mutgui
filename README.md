# mutgui

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**mutgui** - 基于 mutobj 的 Python/C++ GUI 框架。

> **Note:** This package is in early development. Stay tuned for updates.

## 安装

```bash
pip install mutgui
```

## 项目结构

```
mutgui/
├── src/mutgui/       # Python 包
├── csrc/             # C++ 源码
├── tests/            # 测试
└── docs/             # 文档
```

## 开发

```bash
pip install -e ".[dev]"
pytest
```

## 发布

Tag 触发自动发布（PyPI Trusted Publishers，无需 token）：

```bash
git tag v0.1.x
git push origin v0.1.x
```

源码版本保持 `x.y.999`，CI 从 tag 提取正式版本号替换后构建发布。

## License

MIT License - 详见 [LICENSE](LICENSE)
