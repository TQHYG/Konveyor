#!/usr/bin/env bash
#
# Konveyor 简体中文安装器（本复刻专用）
#
# 它在调用原版 install.sh 之前，把 i18n/zh_CN.json 里的中文翻译写入源码树，
# 安装结束后再还原。原版 install.sh 完全保持不变，所以同步上游时不会因为
# 安装脚本产生冲突。
#
# 用法：
#   ./install-zh.sh                 # 更新源码、安装中文版
#   ./install-zh.sh --no-pull       # 不拉取源码，直接用当前代码安装
#   ./install-zh.sh --no-widgets    # 只装窗口管理器（其余参数原样转交 install.sh）
#
# 所有未识别的参数都会原样传给 install.sh，例如 --skip-deps、--no-widgets、--aur。

set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export KONVEYOR_SOURCE_DIR="${KONVEYOR_SOURCE_DIR:-$INSTALL_DIR}"
SOURCE_DIR="$KONVEYOR_SOURCE_DIR"
LANG_CODE="${KONVEYOR_I18N_LANG:-zh_CN}"
I18N_JSON="$SOURCE_DIR/i18n/$LANG_CODE.json"
I18N_TOOL="$SOURCE_DIR/tools/i18n/i18n.py"
PLASMA_SHARED_URL="${KONVEYOR_PLASMA_SHARED_URL:-https://github.com/DevL0rd/Plasma-Shared.git}"
SUBMODULE_PATH="widgets/shared/common"
UPDATE_SOURCE="${XDG_DATA_HOME:-$HOME/.local/share}/konveyor/source"

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }
die() {
    printf '\033[1;31merror:\033[0m %s\n' "$*" >&2
    exit 1
}

usage() {
    cat <<EOF
用法: ./install-zh.sh [选项] [install.sh 的选项]

安装 Konveyor 的简体中文版：先应用 i18n/$LANG_CODE.json，再调用原版
install.sh，结束后还原源码。原版 install.sh 不被修改。

  --no-pull      不拉取上游源码，直接用当前代码安装
  -h, --help     显示本帮助并退出

其余选项（--skip-deps、--no-widgets、--aur 等）会原样传给 install.sh。
EOF
}

SKIP_PULL=false
INSTALL_ARGS=()
for argument in "$@"; do
    case "$argument" in
    --no-pull) SKIP_PULL=true ;;
    -h | --help)
        usage
        exit 0
        ;;
    *) INSTALL_ARGS+=("$argument") ;;
    esac
done

[[ -f $I18N_TOOL ]] || die "找不到翻译工具: $I18N_TOOL"
command -v python3 >/dev/null 2>&1 || die "需要 python3 来应用翻译"
if [[ ! -f $I18N_JSON ]]; then
    warn "找不到语言文件 $I18N_JSON，将按原版安装（不翻译）"
fi
INSTALLER="${KONVEYOR_ZH_INSTALLER:-$SOURCE_DIR/install.sh}"
[[ -x $INSTALLER ]] || die "找不到可执行的 install.sh"

is_git_repo() { git -C "$SOURCE_DIR" rev-parse --git-dir >/dev/null 2>&1; }

# ---------------------------------------------------------------------------
# 1. 把 widgets/shared/common 指向原作者仓库
#
# 复刻默认只复刻主仓库，.gitmodules 里的相对地址 ../Plasma-Shared.git 会解析成
# <你的用户名>/Plasma-Shared.git 而克隆失败。这里把本地 git 配置改成作者的仓库
# （新克隆则由仓库里已改好的 .gitmodules 决定）。
# ---------------------------------------------------------------------------
fix_submodule() {
    is_git_repo || return 0
    git -C "$SOURCE_DIR" config "submodule.$SUBMODULE_PATH.url" "$PLASMA_SHARED_URL"
    return 0
}

# ---------------------------------------------------------------------------
# 2. 更新源码
# ---------------------------------------------------------------------------
update_source() {
    is_git_repo || {
        warn "$SOURCE_DIR 不是 git 仓库，跳过源码更新"
        return 0
    }
    if ! $SKIP_PULL && git -C "$SOURCE_DIR" rev-parse --abbrev-ref '@{upstream}' >/dev/null 2>&1; then
        say "更新源码"
        git -C "$SOURCE_DIR" pull --ff-only || warn "无法拉取更新，继续使用当前代码"
    fi
    say "更新子模块 ($SUBMODULE_PATH)"
    git -C "$SOURCE_DIR" submodule update --init --recursive ||
        die "子模块更新失败；请检查网络，或运行 git submodule update --init --recursive 查看详情"
}

# ---------------------------------------------------------------------------
# 3. 让自动重建也使用中文
#
# Konveyor 会保留一份用于系统更新后自动重建的克隆（默认在
# ~/.local/share/konveyor/source）。我们给这份克隆设置 core.hooksPath，
# 指向仓库里的 i18n/git-hooks/，这样每次 checkout 之后都会自动应用中文，
# 且不需要修改 install.sh。
# ---------------------------------------------------------------------------
install_update_hooks() {
    [[ -d $UPDATE_SOURCE/.git ]] || return 0
    [[ -f $UPDATE_SOURCE/i18n/git-hooks/post-checkout ]] || return 0
    git -C "$UPDATE_SOURCE" config core.hooksPath "$UPDATE_SOURCE/i18n/git-hooks"
    chmod +x "$UPDATE_SOURCE/i18n/git-hooks/"* 2>/dev/null || true
    say "已让系统更新后的自动重建使用中文"
    return 0
}

# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
fix_submodule
update_source

# 应用翻译；无论安装成功与否，退出时都还原源码
# shellcheck source=/dev/null
source "$SOURCE_DIR/i18n/hook.sh"
konveyor_i18n_apply
say "安装 Konveyor"
"$INSTALLER" --no-pull "${INSTALL_ARGS[@]}"

install_update_hooks
say "完成。源码已还原为上游英文版本。"
