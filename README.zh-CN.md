# Konveyor 简体中文版

这是 [DevL0rd/Konveyor](https://github.com/DevL0rd/Konveyor) 的简体中文复刻。
Konveyor 让 KDE Plasma 变成一条可以无限滚动的窗口传送带（类似 niri 的
scrolling tiling），本复刻在**不修改上游源码**的前提下提供中文界面，并能
自动跟随上游更新。

> 上游项目本身的介绍、截图和完整文档请见 [README.md](README.md)。
> 本地化机制的细节见 [i18n/README.md](i18n/README.md)。

## 安装

需要 KDE Plasma 6.7 或更新版本、Wayland 会话。

```sh
git clone --recurse-submodules https://github.com/TQHYG/Konveyor.git
cd Konveyor
./install-zh.sh
```

`install-zh.sh` 会自动：

- 把 `widgets/shared/common` 子模块指向原作者仓库（复刻没有复刻它）；
- 更新源码；
- 在编译前应用 `i18n/zh_CN.json` 中的中文翻译；
- 调用**原版的** `install.sh` 完成构建、安装、启用；
- 安装结束后把源码还原成上游英文版。

常用参数：

```sh
./install-zh.sh --no-pull       # 不拉取更新，直接用当前代码安装
./install-zh.sh --no-widgets    # 只装窗口管理器
./install-zh.sh --skip-deps     # 不安装构建依赖
```

其余参数都会原样传给 `install.sh`。

安装完成后：

- 按 <kbd>Meta</kbd> + <kbd>K</kbd> 打开控制面板（快捷键速查表）；
- 系统设置 → 窗口管理 → Konveyor 打开中文设置界面；
- 配置文件在 `~/.config/konveyor/config.kdl`。

卸载：

```sh
./uninstall.sh
```

## 从 Release 源码包安装

每次上游有更新时，Action 会发布一个源码包（含子模块内容和 `.git`）：

```sh
tar -xzf konveyor-zh-*.tar.gz
cd konveyor-zh
./install-zh.sh
```

## 保持最新

- 本复刻的 `main` 会由 GitHub Action 每天自动合并上游；
- 你只需要定期在本地运行一次：

  ```sh
  git pull
  ./install-zh.sh
  ```

- 系统更新（KWin / Qt / Plasma）触发的自动重建也保持中文：安装时会给
  用于重建的克隆设置 git 钩子，自动重新应用翻译。

## 翻译进度与参与

- 所有界面字符串位于 `i18n/zh_CN.json`，当前 **992/992 已翻译**。
- 上游更新引入新字符串时，Action 会在运行 Summary（或 Issue）里列出。
- 想补充翻译：编辑 `i18n/zh_CN.json`，键是英文原文、值是中文，发 PR 即可。
  也可以运行：

  ```sh
  python3 tools/i18n/i18n.py extract --lang zh_CN   # 补充新词条
  python3 tools/i18n/i18n.py status --verbose       # 查看未翻译项
  ```

## 与上游的关系

为了让同步上游时几乎不产生冲突，本复刻：

- **不修改** `install.sh`，汉化逻辑全部放在 `install-zh.sh` 和 `i18n/`；
- 只把 `.gitmodules` 的子模块地址改成绝对地址（指向
  `DevL0rd/Plasma-Shared`），因为复刻没有复刻插件仓库；
- 其余全是新增文件。

因此 `git merge upstream/main` 通常都能干净合并。

## 已知局限

- Plasma 部件本体（`widgets/**/*.qml`）默认未翻译，只翻译了部件名称与描述。
  扩展方法见 [i18n/README.md](i18n/README.md)。
- C++ 中的字符串（加载失败通知、CLI 帮助）以及速查表里显示的 KWin
  快捷键动作名（来自 kglobalaccel）仍为英文。
