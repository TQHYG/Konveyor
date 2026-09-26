#!/usr/bin/env python3
"""Konveyor translation overlay.

This is the machinery behind Konveyor's out-of-tree localization. Translations
live in independent JSON files (``i18n/<lang>.json``) and the upstream sources
are never left modified: ``apply`` edits the working tree in place while keeping
a backup under ``.git/konveyor-i18n`` and ``revert`` puts the originals back.
The repository therefore stays a clean mirror of upstream, which makes
``git merge upstream/main`` conflict-free.

Commands
--------
extract   Scan the sources and refresh ``i18n/<lang>.json`` with new strings.
status    Report how many strings are translated per language.
apply     Translate the working tree in place (backs up the originals).
revert    Restore the working tree from the backup.
check     Flag dictionary keys that look like code and could break things.

Only ``apply``/``revert`` touch the sources; the rest are read-only.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter, OrderedDict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
I18N_DIR = REPO / "i18n"
BACKUP_ROOT = Path(".git") / "konveyor-i18n"
STATE_FILE = "state.json"

# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

# QML properties whose string value is shown to the user.
QML_UI_PROPS = {
    "text", "label", "title", "description", "placeholderText", "placeholder",
    "explanation", "hint", "tooltip", "summary", "caption", "subtitle",
    "lowLabel", "highLabel", "autoLabel", "addLabel", "unsetLabel",
    "noneLabel", "anyLabel", "yesLabel", "noLabel", "triggerLabel",
    "output", "group", "section", "keywords", "message",
}

# JavaScript object keys whose value is shown to the user.
JS_UI_KEYS = {
    "label", "title", "description", "word", "section", "explanation",
    "caption", "summary", "placeholder", "subtitle", "tooltip", "hint",
    "text", "group", "output", "message",
}

# Files where a normally code object key actually carries UI text.
JS_FILE_ALLOW = {
    "src/settings/qml/catalog/Actions.js": {"dimension"},
    "src/settings/qml/catalog/RuleSummary.js": {"off", "beside", "stack"},
}

# User visible argument positions (1 based) of specific functions.
JS_FUNC_ARGS = {
    "a": {3},
    "monitorFamily": {2},
}

# Functions whose arguments are never UI text.
JS_CODE_FUNCS = {
    "log", "warn", "error", "debug", "info", "qDebug", "qWarning",
    "qCritical", "qCInfo", "require",
    # KDL node builders: their arguments are config keys, never UI text.
    "leaf", "block", "sizeBlock", "sizesBlock", "setValue", "setNode",
    "setBlock", "remove",
}

I18N_FUNCS = {"i18n", "i18nc", "i18nd", "qsTr", "qsTranslate", "tr"}

# Core sources. The Plasma widgets under ``widgets/`` keep their upstream
# ``i18n()`` strings; only their metadata (the name and description shown in
# the widget list) is translated here. Add ``widgets/**/*.qml`` to these globs
# to localise the widget bodies too.
QML_GLOBS = ["src/**/*.qml"]
JS_GLOBS = ["src/**/*.js", "src/**/*.in"]
METADATA_JSON = ["src/kcm/kcm_konveyor.json", "widgets/**/metadata.json"]
METADATA_KEYS = {"Name", "Description", "Comment"}

SKIP_DIRS = {".git", "build", "build-release", "build-i18n", ".i18n", ".konveyor-i18n", "node_modules"}


def looks_like_ui(text: str) -> bool:
    """Heuristic used by ``extract`` so the dictionary stays free of code."""
    if len(text) < 2:
        return False
    if len(re.findall(r"[A-Za-z\u4e00-\u9fff]", text)) < 2:
        return False
    if text.startswith("qrc:") or "://" in text:
        return False
    if re.search(r"[\\/$]", text) and " " not in text:
        return False
    if " " not in text:
        # Single tokens: reject identifiers (SEARCH_LIMIT), dotted names
        # (org.kde.Konveyor, Foo.qml) and all-caps constants.
        if re.search(r"[._]", text) or text.isupper():
            return False
        return re.match(r"[A-Z\u4e00-\u9fff]", text) is not None
    return True


COMMAND_RE = re.compile(
    r"(^|\s)(bash|sh|python3?|node|pkexec|busctl|gdbus|dbus-send|journalctl|systemctl|"
    r"grep|sed|awk|tr|readlink|kill|setsid|xdg-open|konsole|ssh|curl|jq|nmap|mapfile|sudo)\b"
)


def looks_like_command(text: str) -> bool:
    """True for shell snippets embedded in widget QML, which must stay verbatim."""
    stripped = text.strip()
    if not stripped:
        return False
    if stripped[0] in "/$|;\\" or stripped.startswith("--"):
        return True
    if re.search(r"(2?>|>>?)\s*/dev/null", text):
        return True
    if re.search(r"\$\(|\$\{|\$HOME|\$TIDS|\$\{", text):
        return True
    if "| " in text or "&& " in text or "|| " in text:
        return True
    if COMMAND_RE.search(text):
        return True
    if re.search(r"\s-[a-zA-Z]\b", text):
        return True
    return False


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

REGEX_PREV_PUNCT = set("(,=:[!&|?{};+-*%^~<>")
REGEX_PREV_KEYWORDS = {
    "return", "typeof", "case", "in", "of", "new", "delete", "void",
    "instanceof", "do", "else", "yield", "await", "throw",
}


def tokenize(text: str):
    """Yield ``(kind, value, start, end)`` with comments/whitespace removed."""
    i = 0
    n = len(text)
    prev_sig = None
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c == "/":
            regex_position = prev_sig is None or (prev_sig[0] == "punct" and prev_sig[1] in REGEX_PREV_PUNCT) or (
                prev_sig[0] == "id" and prev_sig[1] in REGEX_PREV_KEYWORDS
            )
            if regex_position:
                j = i + 1
                in_class = False
                closed = False
                while j < n:
                    if text[j] == "\\":
                        j += 2
                        continue
                    if text[j] == "[":
                        in_class = True
                    elif text[j] == "]":
                        in_class = False
                    elif text[j] == "/" and not in_class:
                        closed = True
                        break
                    elif text[j] == "\n":
                        break
                    j += 1
                if closed:
                    j += 1
                    while j < n and text[j].isalpha():
                        j += 1
                    prev_sig = ("regex", text[i:j])
                    yield ("regex", text[i:j], i, j)
                    i = j
                    continue
            yield ("punct", "/", i, i + 1)
            prev_sig = ("punct", "/")
            i += 1
            continue
        if c in "\"'`":
            quote = c
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == quote:
                    break
                j += 1
            token = ("str", text[i + 1:j] if j < n else text[i + 1:], i, min(j + 1, n))
            yield token
            prev_sig = ("str", token[1])
            i = j + 1
            continue
        if c.isalpha() or c in "_$":
            j = i
            while j < n and (text[j].isalnum() or text[j] in "_$."):
                j += 1
            token = ("id", text[i:j], i, j)
            yield token
            prev_sig = ("id", text[i:j])
            i = j
            continue
        if c.isdigit():
            j = i
            while j < n and (text[j].isalnum() or text[j] in "._"):
                j += 1
            token = ("num", text[i:j], i, j)
            yield token
            prev_sig = ("num", text[i:j])
            i = j
            continue
        matched = False
        for op in ("===", "!==", "==", "!=", "<=", ">=", "&&", "||", "=>", "?.", "??"):
            if text.startswith(op, i):
                yield ("punct", op, i, i + len(op))
                prev_sig = ("punct", op)
                i += len(op)
                matched = True
                break
        if matched:
            continue
        yield ("punct", c, i, i + 1)
        prev_sig = ("punct", c)
        i += 1


def replace_tokens(text: str, replacements) -> str:
    for start, end, value in sorted(replacements, reverse=True):
        text = text[:start] + value + text[end:]
    return text


def enclosing_call(tokens, idx):
    """Return ``(function_name, argument_index)`` of the innermost call."""
    depth = 0
    argument = 1
    j = idx - 1
    while j >= 0:
        token = tokens[j]
        if token[0] == "punct":
            ch = token[1]
            if ch in ")]}":
                depth += 1
            elif ch in "([{":
                if depth == 0:
                    if ch == "(":
                        prev = tokens[j - 1] if j >= 1 else None
                        name = prev[1].split(".")[-1] if prev and prev[0] == "id" else None
                        return name, argument
                    return None, 1
                depth -= 1
            elif ch == "," and depth == 0:
                argument += 1
        j -= 1
    return None, 1


def colon_is_ternary(tokens, colon_idx):
    """True when the ``:`` at ``colon_idx`` belongs to ``cond ? a : b``."""
    depth = 0
    j = colon_idx - 1
    while j >= 0:
        token = tokens[j]
        if token[0] == "punct":
            ch = token[1]
            if ch in ")]}":
                depth += 1
            elif ch in "([{":
                if depth == 0:
                    return False
                depth -= 1
            elif depth == 0:
                if ch == "?":
                    return True
                if ch in (";", ",", "=", ":"):
                    return False
        j -= 1
    return False


def string_role(tokens, idx, kind, relpath):
    """Classify a string token as ``ui``, ``code`` or ``loose``."""
    prev = tokens[idx - 1] if idx >= 1 else None
    prev2 = tokens[idx - 2] if idx >= 2 else None
    nxt = tokens[idx + 1] if idx + 1 < len(tokens) else None

    # Object key: "foo": ... (but not a ternary consequent, `c ? "a" : "b"`)
    if nxt and nxt[0] == "punct" and nxt[1] == ":" and not colon_is_ternary(tokens, idx + 1):
        return "code"

    # Value of an object property.
    if prev and prev[0] == "punct" and prev[1] == ":" and prev2 and prev2[0] == "id":
        if not colon_is_ternary(tokens, idx - 1):
            key = prev2[1].split(".")[-1]
            ui = QML_UI_PROPS if kind == "qml" else JS_UI_KEYS
            if key in ui:
                return "ui"
            if kind == "js" and key in JS_FILE_ALLOW.get(relpath, set()):
                return "ui"
            return "code"

    # Comparison or import positions.
    if prev and prev[0] == "punct" and prev[1] in ("===", "!==", "==", "!=", "<=", ">="):
        return "code"
    if prev and prev[0] == "id" and prev[1] in ("import", "require", "case"):
        return "code"

    # Function arguments.
    name, argument = enclosing_call(tokens, idx)
    if name:
        if name in JS_CODE_FUNCS:
            return "code"
        if kind == "qml" and name in I18N_FUNCS:
            return "ui"
        if kind == "js" and name in JS_FUNC_ARGS:
            return "ui" if argument in JS_FUNC_ARGS[name] else "code"

    return "loose"


# ---------------------------------------------------------------------------
# Translators
# ---------------------------------------------------------------------------

def quote_literal(text: str, start: int, value: str) -> str:
    """Wrap ``value`` in the same quote the source used, escaping it."""
    quote = text[start] if start < len(text) and text[start] in "\"'`" else '"'
    value = value.replace("\\", "\\\\")
    if quote != "`":
        value = value.replace(quote, "\\" + quote)
    return quote + value + quote


def translate_text(text: str, table: dict, kind: str, relpath: str):
    tokens = list(tokenize(text))
    out = []
    stats = Counter()
    for idx, token in enumerate(tokens):
        if token[0] != "str":
            continue
        value = token[1]
        role = string_role(tokens, idx, kind, relpath)
        if role == "code":
            continue
        if value not in table:
            if role == "ui" and looks_like_ui(value):
                stats["missing"] += 1
            continue
        translated = table[value]
        if translated and translated != value:
            out.append((token[2], token[3], quote_literal(text, token[2], translated)))
            stats["translated"] += 1
        elif not translated:
            stats["missing"] += 1
    return replace_tokens(text, out), stats


def translate_metadata_json(text: str, table: dict):
    stats = Counter()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text, stats
    changed = False

    def apply(node, key=None):
        nonlocal changed
        if isinstance(node, dict):
            for k in list(node.keys()):
                node[k] = apply(node[k], k)
        elif isinstance(node, list):
            node = [apply(v, key) for v in node]
        elif isinstance(node, str) and key in METADATA_KEYS:
            if table.get(node):
                changed = True
                return table[node]
        return node

    data = apply(data)
    if not changed:
        return text, stats
    stats["translated"] += 1
    return json.dumps(data, indent=4, ensure_ascii=False) + "\n", stats


def transform(content: str, relpath: str, table: dict):
    if relpath.endswith(".qml"):
        return translate_text(content, table, "qml", relpath)
    if relpath.endswith((".js", ".in")):
        return translate_text(content, table, "js", relpath)
    if relpath.endswith(".json"):
        return translate_metadata_json(content, table)
    return content, Counter()


# ---------------------------------------------------------------------------
# Files and dictionary
# ---------------------------------------------------------------------------

def iter_files(repo: Path, kind: str):
    seen = set()
    globs = {"qml": QML_GLOBS, "js": JS_GLOBS, "metadata": METADATA_JSON}[kind]
    for pattern in globs:
        for path in sorted(repo.glob(pattern)):
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.relative_to(repo).parts):
                continue
            if path in seen:
                continue
            seen.add(path)
            yield path


def dictionary_path(lang: str) -> Path:
    return I18N_DIR / f"{lang}.json"


def load_dictionary(lang: str):
    path = dictionary_path(lang)
    if not path.exists():
        return OrderedDict()
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("$schema", None)
    data.pop("_comment", None)
    return OrderedDict(data)


def save_dictionary(lang: str, table):
    path = dictionary_path(lang)
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    merged = OrderedDict()
    for key in ("$schema", "_comment"):
        if key in existing:
            merged[key] = existing[key]
    for key in sorted(table.keys(), key=lambda s: (s.lower(), s)):
        merged[key] = table[key]
    path.write_text(json.dumps(merged, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def collect_candidates(repo: Path):
    """Return ``Counter`` of candidate UI strings across the sources."""
    found = Counter()

    def consider(value):
        if not value:
            return
        found[value] += 1

    for kind in ("qml", "js"):
        for path in iter_files(repo, kind):
            rel = str(path.relative_to(repo))
            tokens = list(tokenize(path.read_text(encoding="utf-8")))
            for idx, token in enumerate(tokens):
                if token[0] != "str":
                    continue
                role = string_role(tokens, idx, kind, rel)
                if role == "ui":
                    consider(token[1])
                elif role == "loose" and looks_like_ui(token[1]) and not looks_like_command(token[1]):
                    consider(token[1])

    for path in iter_files(repo, "metadata"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        def walk(node, key=None):
            if isinstance(node, dict):
                for k, v in node.items():
                    walk(v, k)
            elif isinstance(node, list):
                for v in node:
                    walk(v, key)
            elif isinstance(node, str) and key in METADATA_KEYS:
                consider(node)

        walk(data)
    return found


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_extract(args):
    repo = Path(args.repo).resolve()
    table = load_dictionary(args.lang)
    found = collect_candidates(repo)
    added = 0
    for value in found:
        if value not in table:
            table[value] = ""
            added += 1
    untranslated = sum(1 for v in table.values() if not v)
    save_dictionary(args.lang, table)
    print(f"language: {args.lang}")
    print(f"  candidate strings found : {len(found)}")
    print(f"  newly added (empty)     : {added}")
    print(f"  dictionary entries      : {len(table)}")
    print(f"  translated              : {len(table) - untranslated}")
    print(f"  untranslated            : {untranslated}")
    return 0


def cmd_status(args):
    if args.languages:
        languages = args.languages
    else:
        skip = {"languages", "schema"}
        languages = sorted(p.stem for p in I18N_DIR.glob("*.json") if p.stem not in skip)
    if not languages:
        print("no dictionaries found in i18n/")
        return 1
    total = done = 0
    for lang in languages:
        table = load_dictionary(lang)
        untranslated = [k for k, v in table.items() if not v]
        total += len(table)
        done += len(table) - len(untranslated)
        print(f"{lang}: {len(table) - len(untranslated)}/{len(table)} translated ({len(untranslated)} missing)")
        if args.verbose:
            for key in untranslated:
                print(f"    {key}")
    print(f"total: {done}/{total}")
    return 0


def cmd_check(args):
    table = load_dictionary(args.lang)
    risky = []
    for key in table:
        if not key:
            continue
        if re.fullmatch(r"[a-z0-9][a-z0-9._/-]*", key) and " " not in key:
            risky.append((key, "looks like a code identifier"))
    print(f"checked {len(table)} entries, {len(risky)} suspicious")
    for key, why in risky:
        print(f"  [{why}] {key!r}")
    return 0


def cmd_apply(args):
    repo = Path(args.repo).resolve()
    table = load_dictionary(args.lang)
    backup = repo / BACKUP_ROOT
    if (backup / STATE_FILE).exists():
        print("translations already applied; run `revert` first", file=sys.stderr)
        return 1
    touched = []
    stats = Counter()
    for kind in ("qml", "js", "metadata"):
        for path in iter_files(repo, kind):
            rel = str(path.relative_to(repo))
            original = path.read_text(encoding="utf-8")
            translated, st = transform(original, rel, table)
            stats.update(st)
            if translated == original:
                continue
            target = backup / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(original, encoding="utf-8")
            path.write_text(translated, encoding="utf-8")
            touched.append(rel)
    backup.mkdir(parents=True, exist_ok=True)
    (backup / STATE_FILE).write_text(json.dumps({"language": args.lang, "files": touched}, indent=2) + "\n", encoding="utf-8")
    print(f"applied {args.lang}: {len(touched)} files, {stats['translated']} strings")
    return 0


def cmd_revert(args):
    repo = Path(args.repo).resolve()
    backup = repo / BACKUP_ROOT
    state_path = backup / STATE_FILE
    if not state_path.exists():
        print("nothing to revert")
        return 0
    state = json.loads(state_path.read_text(encoding="utf-8"))
    restored = 0
    for rel in state.get("files", []):
        source = backup / rel
        target = repo / rel
        if source.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            restored += 1
    shutil.rmtree(backup, ignore_errors=True)
    print(f"reverted {restored} files")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=str(REPO), help="repository root (default: %(default)s)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("extract", help="refresh the dictionary with new strings")
    p.add_argument("--lang", default="zh_CN")
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("status", help="show translation progress")
    p.add_argument("--languages", nargs="*")
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("check", help="flag dictionary keys that look like code")
    p.add_argument("--lang", default="zh_CN")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("apply", help="translate the working tree in place")
    p.add_argument("--lang", default="zh_CN")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("revert", help="restore the working tree")
    p.set_defaults(func=cmd_revert)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
