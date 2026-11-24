#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""云端续期：把本次刷新得到的新 refreshToken 写回仓库 Secret。

避免 refreshToken（约 30 天）过期后云端签到失效。
优先用 GITHUB_TOKEN（workflow 自带身份）；若被拒则用环境变量 GH_PAT。

用法：python sync_secret.py <owner/repo> <new_rt_file>
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request

SECRET_NAME = "WB_REFRESH_TOKEN"


def api(url, method="GET", body=None, token=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 method=method)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")
    except Exception as e:
        return 0, {"error": str(e)[:200]}


def try_set(repo, rt, token):
    st, pk = api("https://api.github.com/repos/%s/actions/secrets/public-key" % repo, token=token)
    if st != 200:
        return False, "public-key %s %s" % (st, json.dumps(pk, ensure_ascii=False)[:120])
    from nacl.bindings import crypto_box_seal
    key = base64.b64decode(pk["key"])
    enc = base64.b64encode(crypto_box_seal(rt.encode(), key)).decode()
    st, body = api("https://api.github.com/repos/%s/actions/secrets/%s" % (repo, SECRET_NAME),
                   method="PUT", body={"encrypted_value": enc, "key_id": pk["key_id"]}, token=token)
    return st in (201, 204), "HTTP %s %s" % (st, json.dumps(body, ensure_ascii=False)[:150])


def main():
    repo = sys.argv[1]
    rt = open(sys.argv[2], encoding="utf-8").read().strip()
    if not rt:
        print("新 RT 为空，跳过")
        return 2
    cands = []
    if os.environ.get("GITHUB_TOKEN"):
        cands.append(("GITHUB_TOKEN", os.environ["GITHUB_TOKEN"]))
    if os.environ.get("GH_PAT"):
        cands.append(("GH_PAT", os.environ["GH_PAT"]))
    for name, tok in cands:
        ok, msg = try_set(repo, rt, tok)
        print("%s -> %s %s" % (name, "OK" if ok else "FAIL", msg))
        if ok:
            return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
