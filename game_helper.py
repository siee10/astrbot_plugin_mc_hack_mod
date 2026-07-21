"""
Game Helper - 密码破译小游戏辅助模块

游戏规则：四位不重复数字密码（0-9），每次输入会得到每个位置的反馈：
  ✅ 数字正确且位置正确
  🟠 数字正确但位置不对
  ❌ 数字不包含在密码中

监听群聊中的游戏消息，自动推理出下一次尝试的数字。
HTTP 接口返回推理出的下一次尝试结果。
"""

import re
import itertools
from aiohttp import web
from astrbot.api import logger


def _evaluate(guess: str, secret: str) -> list[str]:
    """模拟游戏反馈：对 guess 的每一位返回 ✅ 🟠 ❌。"""
    result = []
    for i, ch in enumerate(guess):
        if ch == secret[i]:
            result.append("✅")
        elif ch in secret:
            result.append("🟠")
        else:
            result.append("❌")
    return result


class CodeBreakerSolver:
    """四位不重复数字密码推理器。"""

    def __init__(self):
        self._all_candidates: list[str] = [
            "".join(p) for p in itertools.permutations("0123456789", 4)
        ]
        self._possible: list[str] = list(self._all_candidates)
        self._attempts: list[tuple[str, list[str]]] = []

    def add_feedback(self, guess: str, feedback: list[str]):
        """添加一次尝试及其反馈，缩小候选集。"""
        self._attempts.append((guess, feedback))
        self._possible = [
            c for c in self._possible
            if _evaluate(guess, c) == feedback
        ]
        logger.info(
            f"[CodeBreaker] 添加反馈: {guess} -> {''.join(feedback)}, "
            f"剩余 {len(self._possible)} 个候选"
        )

    def next_guess(self) -> str | None:
        """返回下一次应该尝试的数字，无可选时返回 None。"""
        if not self._possible:
            return None
        return self._possible[0]

    @property
    def is_solved(self) -> bool:
        return len(self._possible) == 1

    @property
    def attempt_count(self) -> int:
        return len(self._attempts)

    def reset(self):
        """重置推理状态。"""
        self._possible = list(self._all_candidates)
        self._attempts.clear()


class GameHelper:
    """小游戏辅助模块，管理密码破译游戏的推理和 HTTP 接口。"""

    # 匹配一行尝试反馈: 如 "第1次输入: 0🟠丨1❌丨2❌丨3❌"
    ATTEMPT_LINE = re.compile(
        r"第\d+次输入:\s*(\d)([✅🟠❌])[丨|](\d)([✅🟠❌])[丨|](\d)([✅🟠❌])[丨|](\d)([✅🟠❌])"
    )
    # 匹配正确密码行: 🟢正确密码是: 7054
    SOLVED_LINE = re.compile(r"正确密码是:\s*(\d{4})")

    def __init__(self):
        self._solver = CodeBreakerSolver()

    # ---- HTTP 处理函数 ----

    async def handle_get_answer(self, request: web.Request) -> web.Response:
        """获取下一次尝试的数字。"""
        guess = self._solver.next_guess()
        if guess is None:
            return web.json_response({
                "success": False,
                "error": "无可用的候选数字，可能已无解",
            }, status=404)

        return web.json_response({
            "success": True,
            "guess": guess,
            "attempt": self._solver.attempt_count + 1,
            "remaining": len(self._solver._possible),
        })

    async def handle_reset(self, request: web.Request) -> web.Response:
        """重置推理状态。"""
        self._solver.reset()
        return web.json_response({"success": True, "message": "已重置"})

    # ---- 消息处理 ----

    def process_message(self, message_str: str) -> str | None:
        """处理群消息，提取游戏反馈并更新推理状态。

        Args:
            message_str: 消息文本内容。

        Returns:
            如果有新推理结果，返回描述文本；否则返回 None。
        """
        # 1. 检查是否已给出正确答案
        if self.SOLVED_LINE.search(message_str):
            self._solver.reset()
            logger.info("[GameHelper] 游戏已结束，重置推理状态")
            return None

        # 2. 提取尝试反馈行（取最后匹配的一行）
        matches = list(self.ATTEMPT_LINE.finditer(message_str))
        if not matches:
            return None

        last = matches[-1]
        digits = [last.group(i) for i in range(1, 9, 2)]
        icons = [last.group(i) for i in range(2, 10, 2)]

        guess = "".join(digits)
        feedback = icons

        self._solver.add_feedback(guess, feedback)
        next_g = self._solver.next_guess()

        if next_g:
            msg = f"[GameHelper] 第{self._solver.attempt_count + 1}次尝试: {next_g}"
            if self._solver.is_solved:
                msg += " (已确定唯一解)"
            logger.info(f"[GameHelper] {msg}")
            return msg

        return None
