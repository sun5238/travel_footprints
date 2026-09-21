"""切行分类（草案 §2.1）+ `@` 词法（§2.2，完全封闭）。

只做断定行类与切出 token 两件事；时间/地点判别在 skeleton 层结合 time_rules。
无宽容路径：行首无 `@` 的地名文本一律按续行处理，不尝试恢复为地名。
"""

from __future__ import annotations

from dataclasses import dataclass

_AT = "@"
_RELATION = ("->", "~", "～")


@dataclass(frozen=True)
class AtToken:
    """一个 `@` 实体标记：@ 位置与 token 文本（含其字节区间，供剥除原文）。"""

    at: int
    start: int
    end: int
    text: str


def classify_line(raw: str) -> str:
    """返回行类：blank / title / entity / continuation（§2.1 行分类）。"""
    s = raw.strip()
    if not s:
        return "blank"
    if s.startswith("#"):
        return "title"
    if "@" in s:
        return "entity"
    return "continuation"


def lex_at(line: str) -> list[AtToken]:
    """词法规则（§2.2）：见 @ → 跳过（至多一个）空白 → 贪婪取 token。

    token 边界 = 空白 / 关系词(->、~、～) / 行尾 / 下一个 @。
    `@` 与 token 可紧贴；宽容接受 `@ 成都`（跳一个空白再取）。
    """
    tokens: list[AtToken] = []
    i = 0
    n = len(line)
    while i < n:
        if line[i] != _AT:
            i += 1
            continue
        j = i + 1
        if j < n and line[j].isspace():
            j += 1
        start = j
        while j < n:
            ch = line[j]
            if ch.isspace() or ch == _AT or ch in ("~", "～") or line[j : j + 2] == "->":
                break
            j += 1
        if j > start:
            tokens.append(AtToken(at=i, start=start, end=j, text=line[start:j]))
        i = j
    return tokens


def is_relation_char(ch: str) -> bool:
    return ch in ("~", "～")


def split_transport(line: str) -> list[str]:
    """按 `->` 切交通行两段；无 `->` 返回 [整行]。"""
    if "->" not in line:
        return [line]
    return [part.strip() for part in line.split("->")]