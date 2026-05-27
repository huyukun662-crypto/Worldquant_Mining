"""WorldQuant Brain client: auth + concurrent `/simulations` + result cache.

This is the canonical evaluator for the GA miner (`ga_miner.py`). Per
CLAUDE.md the local yfinance backtest does NOT generalize; every Sharpe /
turnover / fitness number we trust comes from WQ Brain's `/simulations`.

Biometric gate (important)
--------------------------
This account (`fin2309381@xmu.edu.my`) is biometric-gated. `POST
/authentication` returns `401 {"inquiry": "..."}` with header
`www-authenticate: persona` whenever there is no recent face verification.
Completing the inquiry requires a live webcam face-scan in the hosted
Persona web flow (withpersona.com) and CANNOT be done headlessly.

After a browser login + face-scan on platform.worldquantbrain.com the
server keeps a grace window (~4h, the auth token's `exp`) during which
basic-auth `POST /authentication` returns `201` directly. Run the miner
inside that window. Outside it, `authenticate()` raises `BiometricRequired`
with instructions.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable

import requests
from requests.auth import HTTPBasicAuth

log = logging.getLogger("wq-client")

AUTH_URL = "https://api.worldquantbrain.com/authentication"
SIM_URL = "https://api.worldquantbrain.com/simulations"
ALPHA_URL = "https://api.worldquantbrain.com/alphas/{}"


class BiometricRequired(RuntimeError):
    """Raised when /authentication demands a Persona face-scan we can't do."""


class AuthError(RuntimeError):
    pass


# Settings that never change in the search. delay is pinned to 0 (D0) by the
# miner; see SETTING_SPACE in ga_miner.py for the evolvable settings.
FIXED_SETTINGS = {
    "instrumentType": "EQUITY",
    "region":         "USA",
    "language":       "FASTEXPR",
    "unitHandling":   "VERIFY",
    "nanHandling":    "OFF",
    "pasteurization": "ON",
    "visualization":  False,
    "maxTrade":       "OFF",
    "testPeriod":     "P0Y0M",
}


def settings_key(settings: dict) -> str:
    """Stable key for caching (only the fields that affect the backtest)."""
    keys = ("region", "universe", "delay", "decay", "neutralization",
            "truncation", "pasteurization")
    return ",".join(f"{k}={settings.get(k)}" for k in keys)


@dataclass
class SimResult:
    ok: bool
    expression: str
    settings: dict
    sharpe: float = 0.0
    turnover: float = 0.0
    fitness: float = 0.0
    returns: float = 0.0
    drawdown: float = 0.0
    margin: float = 0.0
    longCount: int = 0
    shortCount: int = 0
    sub_universe_sharpe: float = 0.0
    checks: list = field(default_factory=list)
    checks_passed: int = 0
    checks_total: int = 0
    op_count: int = 0
    alpha_id: str = ""
    error: str = ""

    def fails(self) -> list[str]:
        """Names of non-PENDING checks that did not PASS."""
        return [c.get("name") for c in self.checks
                if c.get("result") not in ("PASS", "PENDING")]

    def passes_submit(self, turnover_ceiling: float = 0.25) -> bool:
        """True iff this alpha would clear WQ's IS submission gate.

        All IS checks must be PASS (SELF_CORRELATION may be PENDING on a
        fresh account, which is fine), and turnover must respect the user's
        tighter ceiling.
        """
        if not self.ok or not self.checks:
            return False
        if any(c.get("result") not in ("PASS", "PENDING") for c in self.checks):
            return False
        return self.turnover < turnover_ceiling


class WQClient:
    """Authenticated client with a concurrent submit/poll loop and a disk
    cache so re-runs never re-pay for an (expression, settings) pair."""

    def __init__(self, base_path: str | Path = ".",
                 max_concurrent: int = 3,
                 cache_path: str | Path = "cache/wq_sim_cache.json",
                 poll_interval_s: float = 6.0,
                 sim_timeout_s: float = 420.0,
                 throttle_s: float = 0.6):
        self.base_path = Path(base_path)
        self.max_concurrent = max_concurrent
        self.poll_interval_s = poll_interval_s
        self.sim_timeout_s = sim_timeout_s
        self.throttle_s = throttle_s
        self.session: requests.Session | None = None
        self._username = ""
        self.cache_path = self.base_path / cache_path
        self._cache: dict[str, dict] = {}
        if self.cache_path.exists():
            try:
                self._cache = json.loads(self.cache_path.read_text())
            except Exception:
                self._cache = {}

    # -- auth ---------------------------------------------------------------
    def _read_credentials(self) -> tuple[str, str]:
        for name in ("credential.txt", "credentials.txt"):
            p = self.base_path / name
            if p.exists():
                content = p.read_text(encoding="utf-8").strip()
                try:
                    creds = json.loads(content)
                    if isinstance(creds, list) and len(creds) >= 2:
                        return creds[0], creds[1]
                except json.JSONDecodeError:
                    pass
                lines = [l.strip() for l in content.splitlines() if l.strip()]
                if len(lines) >= 2:
                    return lines[0], lines[1]
        raise AuthError("no credential.txt / credentials.txt found")

    def authenticate(self, retries: int = 3) -> None:
        user, pw = self._read_credentials()
        sess = requests.Session()
        auth = HTTPBasicAuth(user, pw)
        last = None
        for attempt in range(retries):
            r = sess.post(AUTH_URL, auth=auth, timeout=20)
            if r.status_code == 201:
                sess.auth = auth
                self.session = sess
                self._username = user
                body = {}
                try:
                    body = r.json()
                except Exception:
                    pass
                uid = (body.get("user") or {}).get("id", "?")
                log.info(f"authenticated as {user} (id={uid})")
                return
            last = r
            # Biometric / persona challenge -> cannot proceed headlessly.
            if r.status_code == 401 and (
                    "persona" in r.headers.get("www-authenticate", "").lower()
                    or '"inquiry"' in r.text):
                if attempt < retries - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise BiometricRequired(
                    "WQ Brain requires a Persona face-scan for this account. "
                    "Log in at https://platform.worldquantbrain.com, complete "
                    "the biometric verification, then re-run within the grace "
                    "window. (inquiry=%s)" % (r.text[:80]))
            time.sleep(2 * (attempt + 1))
        raise AuthError(f"authentication failed: "
                        f"{getattr(last, 'status_code', '?')} "
                        f"{getattr(last, 'text', '')[:200]}")

    # -- cache --------------------------------------------------------------
    def _flush_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self._cache, indent=1))

    @staticmethod
    def _cache_key(expr: str, settings: dict) -> str:
        return f"{expr}||{settings_key(settings)}"

    # -- low-level request helpers -----------------------------------------
    def _post_sim(self, expr: str, settings: dict) -> tuple[str | None, str]:
        full = dict(FIXED_SETTINGS); full.update(settings)
        body = {"type": "REGULAR", "settings": full, "regular": expr}
        for _ in range(5):
            r = self.session.post(SIM_URL, json=body, timeout=30)
            if r.status_code == 429:
                wait = float(r.headers.get("Retry-After") or 15)
                log.info(f"   429 on submit; sleep {wait:.0f}s")
                time.sleep(wait)
                continue
            if r.status_code == 201:
                return r.headers.get("Location"), ""
            return None, f"submit-{r.status_code}: {r.text[:200]}"
        return None, "submit-429-exhausted"

    def _result_from_alpha(self, expr: str, settings: dict,
                           alpha_id: str, ay: dict) -> SimResult:
        isb = ay.get("is") or {}
        checks = isb.get("checks") or []
        sub = 0.0
        for c in checks:
            if c.get("name") == "LOW_SUB_UNIVERSE_SHARPE":
                sub = float(c.get("value") or 0.0)
        op_count = ((ay.get("regular") or {}).get("operatorCount")) or 0
        return SimResult(
            ok=True, expression=expr, settings=settings,
            sharpe=float(isb.get("sharpe") or 0.0),
            turnover=float(isb.get("turnover") or 0.0),
            fitness=float(isb.get("fitness") or 0.0),
            returns=float(isb.get("returns") or 0.0),
            drawdown=float(isb.get("drawdown") or 0.0),
            margin=float(isb.get("margin") or 0.0),
            longCount=int(isb.get("longCount") or 0),
            shortCount=int(isb.get("shortCount") or 0),
            sub_universe_sharpe=sub,
            checks=checks,
            checks_passed=sum(1 for c in checks if c.get("result") == "PASS"),
            checks_total=len(checks),
            op_count=int(op_count),
            alpha_id=alpha_id,
        )

    # -- concurrent evaluate ------------------------------------------------
    def evaluate_many(self, jobs: list[tuple[str, dict]],
                      use_cache: bool = True) -> dict[str, SimResult]:
        """Evaluate (expression, settings) pairs on WQ Brain, keeping up to
        `max_concurrent` simulations in flight. Returns {cache_key: SimResult}.
        """
        out: dict[str, SimResult] = {}
        queue: list[tuple[str, str, dict]] = []  # (key, expr, settings)
        seen_keys: set[str] = set()
        for expr, settings in jobs:
            key = self._cache_key(expr, settings)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            if use_cache and key in self._cache:
                out[key] = SimResult(**{k: v for k, v in self._cache[key].items()
                                        if k in SimResult.__dataclass_fields__})
                continue
            queue.append((key, expr, settings))

        # progress_url -> (key, expr, settings, t0)
        inflight: dict[str, tuple[str, str, dict, float]] = {}
        n_total = len(queue)
        done = 0

        while queue or inflight:
            # fill the pipe
            while queue and len(inflight) < self.max_concurrent:
                key, expr, settings = queue.pop(0)
                loc, err = self._post_sim(expr, settings)
                if loc is None:
                    res = SimResult(ok=False, expression=expr,
                                    settings=settings, error=err)
                    out[key] = res
                    self._cache[key] = asdict(res)
                    done += 1
                    log.info(f"   [{done}/{n_total}] submit-fail: {err[:70]}")
                else:
                    inflight[loc] = (key, expr, settings, time.time())
                    log.info(f"   submitted ({len(inflight)} in flight): "
                             f"{expr[:70]}")
                time.sleep(self.throttle_s)

            if not inflight:
                continue
            time.sleep(self.poll_interval_s)

            for loc in list(inflight.keys()):
                key, expr, settings, t0 = inflight[loc]
                try:
                    rp = self.session.get(loc, timeout=30)
                except requests.RequestException:
                    continue
                if rp.status_code == 429:
                    continue
                if rp.status_code != 200:
                    if time.time() - t0 > self.sim_timeout_s:
                        res = SimResult(ok=False, expression=expr,
                                        settings=settings,
                                        error=f"poll-{rp.status_code}")
                        out[key] = res; self._cache[key] = asdict(res)
                        del inflight[loc]; done += 1
                    continue
                data = rp.json()
                st = data.get("status", "")
                if st == "COMPLETE":
                    aid = data.get("alpha") or ""
                    ra = self.session.get(ALPHA_URL.format(aid), timeout=30)
                    if ra.status_code == 200:
                        res = self._result_from_alpha(expr, settings, aid, ra.json())
                    else:
                        res = SimResult(ok=False, expression=expr,
                                        settings=settings, alpha_id=aid,
                                        error=f"alpha-get-{ra.status_code}")
                    out[key] = res; self._cache[key] = asdict(res)
                    del inflight[loc]; done += 1
                    mk = "OK " if res.ok else "ERR"
                    log.info(f"   [{done}/{n_total}] {mk} SH={res.sharpe:+.2f} "
                             f"TO={res.turnover:.3f} FIT={res.fitness:+.2f} "
                             f"checks={res.checks_passed}/{res.checks_total} "
                             f"{expr[:55]}")
                elif st in ("ERROR", "FAILED", "WARNING"):
                    res = SimResult(ok=False, expression=expr, settings=settings,
                                    error=f"sim-{st}: {data.get('message','')[:160]}")
                    out[key] = res; self._cache[key] = asdict(res)
                    del inflight[loc]; done += 1
                    log.info(f"   [{done}/{n_total}] ERR {res.error[:70]}")
                elif time.time() - t0 > self.sim_timeout_s:
                    res = SimResult(ok=False, expression=expr, settings=settings,
                                    error="poll-timeout")
                    out[key] = res; self._cache[key] = asdict(res)
                    del inflight[loc]; done += 1
            self._flush_cache()

        self._flush_cache()
        return out
