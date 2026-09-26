# Konveyor 简体中文本地化

这个目录把 Konveyor 汉化成简体中文，同时**不改动上游源码文件**，因此
`git merge upstream/main` 永远不会有（或极少有）冲突，并且可以通过 GitHub
Action 自动跟随上游更新。

- 翻译内容：`i18n/zh_CN.json`（唯一的语言文件）
- 工具：`tools/i18n/i18n.py`（提取 / 应用 / 还原 / 统计）
- 构建挂钩：`i18n/hook.sh`，由 `install.sh` 中四处带注释的钩子调用
- 自动同步：`.github/workflows/sync-upstream.yml`

当前状态：设置界面（KCM / 设置页 / 快捷键速查表）与部件元数据的全部 965
条字符串均已翻译。

## 它是怎么工作的

上游的 Konveyor 把设置界面的 QML **编译进** 插件（`libkonveyor_settings.so`
里是 Qt 资源），所以安装完成后再改磁盘上的 `.qml` 文件是无效的：必须在
**编译之前**把译文写进源码。做法是：

1. `install.sh` 在构建前调用 `konveyor_i18n_apply`；
2. `tools/i18n/i18n.py apply` 按 `i18n/zh_CN.json` 改写工作区里的
   `.qml` / `.js` / 元数据 `.json`，并把原始内容备份到 `.git/konveyor-i18n/`；
3. 照常编译、安装；
4. `install.sh` 退出时（`EXIT` trap）调用 `konveyor_i18n_revert`，把源码
   还原成上游的英文版本。

因此工作区平时始终是上游的干净镜像，只有新增文件（`i18n/`、`tools/i18n/`、
工作流）和 `install.sh` 里那几行钩子是你的。

## 日常使用

```sh
./install.sh                 # 照常安装，自动应用中文翻译
./install.sh --no-widgets    # 只装窗口管理器
```

如果构建意外中断，源码可能停留在已翻译状态，手动还原即可：

```sh
python3 tools/i18n/i18n.py revert
```

## 翻译新字符串

上游更新后会出现新的英文界面文字。刷新词条：

```sh
python3 tools/i18n/i18n.py extract --lang zh_CN
python3 tools/i18n/i18n.py status  --lang zh_CN            # 概览
python3 tools/i18n/i18n.py status  --lang zh_CN --verbose  # 列出未翻译项
```

然后编辑 `i18n/zh_CN.json`，把空字符串填成中文即可：

```json
{
    "Keyboard Shortcuts": "键盘快捷键",
    "Motion": "运动"
}
```

要点：

- **键是英文原文，值是中文译文。** 键必须与源码完全一致，包括首尾空格
  （有些片段是拼接用的，例如 `"by"`、`" px"`）。
- 不要翻译代码值。像动作 id（`focus-column-left`）、配置键、图标名这类
  字符串绝不要加进词典；工具本身也会自动跳过大多数代码位置。
- `%1`、`%2` 是占位符，翻译时保留。
- 想检查有没有误把代码当界面文字加进去：

  ```sh
  python3 tools/i18n/i18n.py check --lang zh_CN
  ```

## 新增一种语言

1. 复制 `i18n/zh_CN.json` 为 `i18n/<语言>.json`（例如 `ja.json`）。
2. 翻译后，在 `i18n/languages.json` 里登记。
3. 安装时指定语言：`KONVEYOR_I18N_LANG=ja ./install.sh`。

`i18n.py` 的 `--lang` 参数对所有子命令都可用。

## 覆盖范围

- `src/**/*.qml`、`src/**/*.js`：设置界面、快捷键速查表、组件。
- `src/kcm/kcm_konveyor.json`、`widgets/**/metadata.json`：系统设置页和
  “添加部件”列表里的名称与描述。
- Plasma 部件本体（`widgets/**/*.qml`）默认**不翻译**。它们原本就用
  `i18n()` 包好了字符串，如果你也想汉化，把
  `tools/i18n/i18n.py` 顶部 `QML_GLOBS` / `JS_GLOBS` 加上
  `widgets/**/*.qml`、`widgets/**/*.js`，再运行 `extract` 即可。注意部件
  QML 里混有大量 shell 命令字符串，`extract` 已内置命令过滤，翻译时仍要
  小心不要把命令翻译掉。

## 上游自动同步

`.github/workflows/sync-upstream.yml` 每天（也可手动触发）执行：

1. 把 `DevL0rd/Konveyor` 的 `main` 合并进本复刻的 `main`；
2. 运行 `extract` 补充新词条；
3. 提交并推送；
4. 如果合并冲突，或出现未翻译字符串，就开一个 Issue 提醒你。

因为我们对上游源码的改动仅限于 `install.sh` 中四处很短的钩子，正常合并
不会冲突；万一冲突，工作流会保留现场并开 Issue，你在本地解决即可。

## 快速了解 `install.sh` 里的钩子

在 `install.sh` 中搜索 `Konveyor Chinese localization (fork)`，共有四处：

- 加载 `i18n/hook.sh`
- `build()` 开头：应用翻译
- `system_update()` 中：在切到 `--finish-update` 子进程前还原
- `finish_update()` 开头：应用翻译（让部件安装阶段也拿到中文）
