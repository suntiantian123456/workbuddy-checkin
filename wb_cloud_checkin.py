#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WorkBuddy 云端每日签到（GitHub Actions 用）。

只用 stdlib + 环境变量 WB_REFRESH_TOKEN：
  1. 用 refreshToken 换 accessToken
  2. 查签到状态并领每日签到（幂等：已签到返回 400/10001 视为成功）
  3. 打印连签天数 / 本月累计 / 补登卡余额 / 连登兑换档位状态
输出直接进 Actions 日志，方便在 GitHub 上看。

注意：refreshToken 有效期约 30 天。同一枚 RT 可重复刷新换新 AT，
但过期后需从本机重新导出并更新仓库 Secret（WB_REFRESH_TOKEN）。
"""
import datetime
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

REFRESH_URL = "https://copilot.tencent.com/v2/plugin/auth/token/refresh"
BASE = "https://www.codebuddy.cn"
CTX = ssl.create_default_context()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
BJT = datetime.timezone(datetime.timedelta(hours=8))


def log(msg):
    print("[%s] %s" % (datetime.datetime.now(BJT).strftime("%Y-%m-%d %H:%M:%S"), msg),
          flush=True)


def request(method, url, headers=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", UA)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=45, context=CTX) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, {"raw": raw[:400]}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw[:400]}
    except Exception as e:
        return 0, {"error": "%s: %s" % (type(e).__name__, str(e)[:200])}


def dig(obj, key, default=None):
    cur = obj
    for part in key.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and cur:
            cur = cur[0]
        else:
            return default
        if cur is None:
            return default
    return cur


def refresh(rt):
    code, body = request("POST", REFRESH_URL,
                         {"X-Refresh-Token": rt, "X-Auth-Refresh-Source": "plugin"}, {})
    at = dig(body, "data.accessToken") or dig(body, "accessToken")
    if code == 200 and at:
        return at, dig(body, "refreshToken") or rt
    return None, "refresh failed: HTTP %s %s" % (code, json.dumps(body, ensure_ascii=False)[:200])


def main():
    rt = os.environ.get("WB_REFRESH_TOKEN", "").strip()
    if not rt:
        log("缺少 WB_REFRESH_TOKEN 环境变量")
        return 2
    at, new_rt = refresh(rt)
    if not at:
        log("❌ 刷新令牌失败：%s" % new_rt)
        log("   需要在本机重新导出并更新仓库 Secret（WB_REFRESH_TOKEN）")
        return 1
    log("✅ 令牌刷新成功")
    if new_rt and new_rt != rt:
        # 把轮换后的新 RT 落盘，由 sync_secret.py 写回仓库 Secret
        try:
            open("new_rt.txt", "w", encoding="utf-8").write(new_rt)
            log("已写出新 refreshToken 待回写 Secret")
        except Exception as e:
            log("写 new_rt.txt 失败: %s" % e)
    h = {"Authorization": "Bearer " + at}

    code, body = request("POST", BASE + "/v2/billing/meter/checkin-activity-status", h, {})
    st = dig(body, "data.active")
    streak = dig(body, "data.streak_days")
    credit = dig(body, "data.today_credit")
    log("签到状态: active=%s 连签=%s 天 今日积分=%s" % (st, streak, credit))

    code, body = request("POST", BASE + "/v2/billing/meter/daily-checkin", h, {})
    if code == 200:
        log("✅ 签到成功")
    elif code == 400 and (dig(body, "code") == 10001 or "已签到" in str(dig(body, "msg"))):
        log("✅ 今日已签到（幂等跳过）")
    else:
        log("⚠️ 签到返回 HTTP %s %s" % (code, json.dumps(body, ensure_ascii=False)[:200]))

    code, body = request("GET", BASE + "/v2/activity/growth/streak", h)
    d = body.get("data") or {}
    log("真实连签=%s 天 本月累计=%s 天 补登卡=%s/%s" % (
        dig(d, "streak.days"), dig(d, "streak.month_total_days"),
        dig(d, "makeup_cards.balance"), dig(d, "makeup_cards.max")))
    rs = d.get("redemption_status") or {}
    log("连登兑换: 7d=%s 14d=%s 28d=%s" % (
        rs.get("tier_7d_status"), rs.get("tier_14d_status"), rs.get("tier_28d_status")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
