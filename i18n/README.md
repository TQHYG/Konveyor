# Konveyor 简体中文本地化

这个复刻把 Konveyor 汉化成简体中文，同时**不修改上游源码**（只改了一行
`.gitmodules` 把子模块指向原作者仓库），因此 `git merge upstream/main`
几乎不会冲突，并且可以通过 GitHub Action 自动跟随上游更新、自动打包发布。

- 安装入口：`install-zh.sh`
- 翻译内容：`i18n/zh_CN.json`（唯一的语言文件）
- 工具：`tools/i18n/i18n.py`（提取 / 应用 / 还原 / 统计）
- 自动同步与发布：`.github/workflows/sync-upstream.yml`

当前状态：设置界面（KCM / 设置页 / 快捷键速查表）与部件元数据共
**992 条字符串全部已翻译**。

## 为什么需要 `install-zh.sh`

上游 Konveyor 把设置界面的 QML **编译进**插件（`libkonveyor_settings.so`
内部是 Qt 资源），所以装好以后再改磁盘上的 `.qml` 没用：必须在**编译之前**
把译文写进源码。

`install-zh.sh` 的做法是：

1. 修正 `widgets/shared/common` 子模块地址（复刻没有复刻插件仓库）；
2. 在需要时 `git pull` 更新源码、`git submodule update`；
3. 调用 `tools/i18n/i18n.py apply` 按 `i18n/zh_CN.json` 改写工作区里的
   `.qml` / `.js` / 元数据 `.json`，原文件备份到 `.git/konveyor-i18n/`；
4. 调用**原封不动的** `./install.sh --no-pull`；
5. 退出时（`EXIT` trap）自动还原源码。

所以工作区平时始终是上游的干净版本，你的改动只有：`install-zh.sh`、
`i18n/`、`tools/i18n/`、工作流，以及 `.gitmodules` 一行。

> 为什么用 `--no-pull`？因为第 3 步已经把源码改成了中文，如果让
> `install.sh` 再 `git pull` 会因为本地修改而失败。源码更新由
> `install-zh.sh` 自己先完成。

## 日常使用

```sh
git clone --recurse-submodules https://github.com/TQHYG/Konveyor.git
cd Konveyor
./install-zh.sh                 # 更新源码并安装中文版
./install-zh.sh --no-pull       # 不拉取更新，直接安装当前代码
./install-zh.sh --no-widgets    # 只装窗口管理器
./install-zh.sh --skip-deps     # 不装依赖
```

未识别的参数会原样传给 `install.sh`。想临时关闭汉化：

```sh
KONVEYOR_I18N_LANG=en ./install-zh.sh   # 没有 en.json 时等于不翻译
```

如果构建中断，源码可能停在已翻译状态，手动还原即可：

```sh
python3 tools/i18n/i18n.py revert
```

## 系统更新后仍然保持中文

Konveyor 会在 `~/.local/share/konveyor/source` 保留一份用于“系统更新后
自动重建”的克隆。`install-zh.sh` 会给这份克隆设置：

```sh
git config core.hooksPath <update-source>/i18n/git-hooks
```

于是它每次被刷新（`git checkout` / `git merge`）后，`i18n/git-hooks/`
里的钩子都会自动重新应用中文。这样 KWin / Qt / Plasma 更新触发的自动重建
依然是中文版，而且完全没有改动 `install.sh`。

## 翻译新字符串

上游更新后会出现新的界面文字。刷新词条：

```sh
python3 tools/i18n/i18n.py extract --lang zh_CN
python3 tools/i18n/i18n.py status                       # 概览
python3 tools/i18n/i18n.py status --verbose             # 列出未翻译项
```

然后编辑 `i18n/zh_CN.json`，把空字符串填成中文：

```json
{
    "Keyboard Shortcuts": "键盘快捷键",
    "Motion": "运动"
}
```

要点：

- **键是英文原文，值是中文译文。** 键必须与源码完全一致，包括首尾空格
  （有些片段是拼接用的，例如 `"by"`、`" px"`）。
- 不要翻译代码值（动作 id、配置键、图标名等）。工具会自动跳过大多数
  代码位置，也可以用 `python3 tools/i18n/i18n.py check` 检查可疑词条。
- `%1`、`%2` 是占位符，翻译时保留。

## 新增一种语言

1. 复制 `i18n/zh_CN.json` 为 `i18n/<语言>.json`（例如 `ja.json`）。
2. 翻译后在 `i18n/languages.json` 登记。
3. 安装时指定：`KONVEYOR_I18N_LANG=ja ./install-zh.sh`。

## 覆盖范围

- `src/**/*.qml`、`src/**/*.js`、`src/**/*.in`：设置界面、快捷键速查表、
  速查表的 Python 生成脚本。
- `src/kcm/kcm_konveyor.json`、`widgets/**/metadata.json`：系统设置页和
  “添加部件”列表中的名称与描述。
- Plasma 部件本体（`widgets/**/*.qml`）默认**不翻译**。它们原本用
  `i18n()` 包好了字符串；想汉化的话，把 `tools/i18n/i18n.py` 顶部的
  `QML_GLOBS` / `JS_GLOBS` 加上 `widgets/**/*.qml`、`widgets/**/*.js`，
  再运行 `extract` 即可。注意部件 QML 里混有大量 shell 命令字符串，
  `extract` 已内置命令过滤，翻译时仍要小心。

## 上游自动同步与发布

`.github/workflows/sync-upstream.yml` 每天（也可手动触发）执行：

1. 把 `DevL0rd/Konveyor` 的 `main` 合并进本复刻的 `main`（无冲突时）；
2. 运行 `extract` 补充新词条；
3. 提交并推送；
4. 有变化时打包完整源码（含 `widgets/shared/common` 子模块内容，并保留
   `.git`，解压后可直接 `./install-zh.sh`）并发布 Release；
5. 合并冲突或出现未翻译字符串时，写入本次运行的 Summary，并（如果仓库
   启用了 Issues）开 Issue 提醒。

> 仓库默认关闭了 Issues。想收通知请在 **Settings → Features** 勾选
> **Issues**；否则在 **Actions → Sync upstream** 查看每次运行顶部的 Summary。
