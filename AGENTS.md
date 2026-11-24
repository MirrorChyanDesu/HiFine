# HiFine 开发指引

HiFine 是面向 Windows、macOS 和 Linux 的桌面图片查看器。通用功能放在 `src/hifine/`，文件管理器集成和安装包按平台放在 `packaging/`。

- 改图片解码或元数据时，从 `imaging.py` 和 `tests/test_imaging.py` 入手。改界面交互时，从 `viewer.py`、`canvas.py` 和 `tests/test_viewer.py` 入手。
- 改文件关联、缩略图或打包逻辑时，用目标平台的安装包验证实际入口。各平台的检查命令可查 [.github/workflows/desktop.yml](.github/workflows/desktop.yml)。
- 提交使用 MistEO 身份。提交前核对 Git 的 author 和 committer，推送前核对实际推送凭据对应的 GitHub 账号。

在仓库根目录激活虚拟环境后，常用命令如下。

```sh
python -m pip install -e ".[build,test]"
python -m hifine
python -m pytest -q
```

用户可见行为变更时同步更新 [README.md](README.md)。安装和发版步骤也维护在那里。
