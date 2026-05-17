"""30分钟心跳：读取本地报告，emit中文摘要行。Monitor会把每行变成通知。"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROBE = REPO / "constants" / "d0_field_universe_matrix.json"
MINING = REPO / "WQ_D0_MINING_REPORT.json"
SUBMIT = REPO / "WQ_D0_SUBMISSION_RESULTS.json"
INTERVAL = 1800  # 30 min


def stage() -> str:
    if SUBMIT.exists():
        try:
            d = json.load(open(SUBMIT))
            if any(x.get("submitted") for x in d):
                return "已提交"
        except Exception:
            pass
    if MINING.exists():
        return "自适应迭代"
    if PROBE.exists():
        try:
            d = json.load(open(PROBE))
            if d.get("d0_enabled"):
                return "probe-OK-待生成"
            # 区分明确400 vs 429/超时
            probes = d.get("probes", [])
            for p in probes:
                b = p.get("body") or ""
                if p.get("status") == 400 and "Delay 0" in b:
                    return "probe-D0被封(HTTP400)"
            return "probe-未通过(并发/超时)"
        except Exception:
            return "probe-中"
    return "probe-中"


def best(records: list[dict]) -> dict | None:
    ok = [r for r in records if r.get("ok") and r.get("sharpe") is not None]
    if not ok:
        return None
    return max(ok, key=lambda r: (
        r.get("checks_passed", 0),
        r.get("sharpe", -999),
    ))


def summary() -> str:
    st = stage()
    sims = 0
    best_line = "暂无候选"
    if MINING.exists():
        try:
            d = json.load(open(MINING))
            sims = len(d)
            b = best(d)
            if b:
                best_line = (
                    f"SH={b.get('sharpe'):.3f} "
                    f"TO={b.get('turnover'):.3f} "
                    f"FIT={b.get('fitness'):.3f} "
                    f"checks={b.get('checks_passed',0)}/{b.get('checks_total',0)}"
                )
        except Exception as e:
            best_line = f"读mining报告失败:{e}"
    ts = time.strftime("%H:%M")
    return f"[心跳 {ts}] 阶段={st} | WQ模拟次数={sims} | 最佳={best_line}"


def main() -> int:
    # 启动后立刻emit一次，方便确认订阅生效
    print(summary(), flush=True)
    while True:
        time.sleep(INTERVAL)
        print(summary(), flush=True)


if __name__ == "__main__":
    sys.exit(main())
