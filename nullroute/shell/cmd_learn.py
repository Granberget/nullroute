"""Learning commands: learn, achievements, tips."""

from __future__ import annotations

from ..game import learning as L
from .commands import cmd
from .core import Ctx


def _show_lesson(ctx: Ctx, num: int) -> None:
    lesson = L.LESSONS[num - 1]
    done = num in ctx.game.state.lessons_done
    ctx.write(f"Lesson {num}/{len(L.LESSONS)}: {lesson.title}" + ("   ✓ done" if done else ""), "title")
    ctx.write("")
    for line in lesson.intro.splitlines():
        ctx.write("  " + line)
    ctx.write("")
    ctx.write("Task:", "tutorial")
    for line in lesson.task.splitlines():
        ctx.write("  " + line, "tutorial")
    ctx.write("")
    how = "learn answer <your answer>" if lesson.needs_answer else "learn check"
    ctx.write(f"When you're done: {how}     Stuck? learn hint", "dim")


def _finish(ctx: Ctx, num: int, msg: str) -> None:
    s = ctx.game.state
    ctx.write(f"✓ {msg}", "good")
    if num not in s.lessons_done:
        s.lessons_done.add(num)
        s.money += L.LESSON_REWARD
        ctx.write(f"Lesson {num} complete! +¢{L.LESSON_REWARD} from the Blackrelay training fund.", "good")
    if len(s.lessons_done) == len(L.LESSONS):
        ctx.game.award("lessons_all")
    nxt = next((i for i in range(1, len(L.LESSONS) + 1) if i not in s.lessons_done), None)
    if nxt:
        ctx.write(f"Next up: learn {nxt}  ({L.LESSONS[nxt - 1].title})", "dim")
    else:
        ctx.write("You've finished every lesson. The rest you learn on the job.", "dim")


@cmd("learn", "short Linux lessons with checked exercises", "learn [N | check | answer X | hint]",
     "Ten bite-sized lessons on the Linux basics, each with a small task that\n"
     "the game checks for you. You earn a few credits for each one.\n"
     "  learn              list the lessons\n"
     "  learn 3            start lesson 3 (sets up its files in ~/learn/03)\n"
     "  learn check        check a task that is about doing something\n"
     "  learn answer 42    answer a task that asks a question\n"
     "  learn hint         show the solution if you're stuck", group="learn")
async def c_learn(ctx: Ctx) -> int:
    s = ctx.game.state
    args = ctx.args
    if not args:
        ctx.write("Linux lessons", "title")
        for i, lesson in enumerate(L.LESSONS, 1):
            mark = "✓" if i in s.lessons_done else "▸" if i == s.lesson_current else " "
            ctx.write(f"  {mark} {i:>2}. {lesson.title}", "good" if i in s.lessons_done else None)
        ctx.write(f"\n{len(s.lessons_done)}/{len(L.LESSONS)} done. Start one with: learn <number>", "dim")
        return 0
    sub = args[0]
    if sub.isdigit():
        num = int(sub)
        if not 1 <= num <= len(L.LESSONS):
            ctx.err(f"there is no lesson {num} (1-{len(L.LESSONS)})")
            return 1
        if not ctx.at_gateway:
            ctx.err("lessons run on your own gateway - exit first")
            return 1
        s.lesson_current = num
        L.LESSONS[num - 1].setup(ctx.game)
        _show_lesson(ctx, num)
        return 0
    num = s.lesson_current
    if not num:
        ctx.err("no lesson started yet - try: learn 1")
        return 1
    lesson = L.LESSONS[num - 1]
    if sub == "hint":
        ctx.write(f"Hint for lesson {num}:", "title")
        ctx.write("  " + lesson.hint)
        return 0
    if sub in ("check", "answer"):
        answer = " ".join(args[1:]) if sub == "answer" else None
        if lesson.needs_answer and answer is None:
            ctx.write("This lesson asks a question: learn answer <your answer>")
            return 1
        ok, msg = lesson.check(ctx.game, answer)
        if ok:
            _finish(ctx, num, msg)
            return 0
        ctx.write(f"✗ {msg}", "warn")
        return 1
    if sub in ("show", "task"):
        _show_lesson(ctx, num)
        return 0
    ctx.err(f"unknown option '{sub}' (try: learn, learn 1, learn check, learn hint)")
    return 1


@cmd("achievements", "list your achievements", "achievements", group="learn")
async def c_achievements(ctx: Ctx) -> int:
    got = ctx.game.state.achievements
    ctx.write(f"Achievements  {len(got)}/{len(L.ACHIEVEMENTS)}", "title")
    for key, (title, desc) in L.ACHIEVEMENTS.items():
        if key in got:
            ctx.write(f"  ★ {title:<22} {desc}", "good")
        else:
            ctx.write(f"  ☆ {title:<22} {desc}", "dim")
    return 0


@cmd("tips", "turn the learning tips on or off", "tips [on|off|reset]", group="learn")
async def c_tips(ctx: Ctx) -> int:
    s = ctx.game.state
    if not ctx.args:
        ctx.write(f"Tips are {'on' if s.tips_enabled else 'off'}. "
                  f"{len(s.tips_seen)}/{len(L.TIPS)} seen.  (tips on | tips off | tips reset)")
        return 0
    arg = ctx.args[0]
    if arg in ("on", "off"):
        s.tips_enabled = arg == "on"
        ctx.write(f"Tips turned {arg}.")
    elif arg == "reset":
        s.tips_seen.clear()
        ctx.write("You'll see every tip again.")
    else:
        ctx.err("use: tips on | tips off | tips reset")
        return 1
    return 0
