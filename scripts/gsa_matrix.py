#!/usr/bin/env python3
"""Đo THỰC TẾ: machine-id của một server anisette có được GSA chấp nhận không,
khi khai báo từng danh tính (client-info) khác nhau.

Chỉ gửi `o=init` với Apple ID KHÔNG TỒN TẠI -> không mật khẩu, không đụng tài khoản.

Cách đọc kết quả:
  ec=-20970 / ec=0   -> danh tính ĐƯỢC CHẤP NHẬN (đi tới bước kiểm tra account)
  ec=-80045          -> Apple từ chối machine-id vì lệch platform
  HTTP 503 + HTML    -> edge chặn danh tính (thường là client-info Android)
  HTTP 429           -> rate limit, không kết luận được
"""
import json
import os
import plistlib
import secrets
import sys
import time

import requests
import urllib3

urllib3.disable_warnings()

GSA = "https://gsa.apple.com/grandslam/GsService2"
UA_AKD = "akd/1.0 CFNetwork/808.1.4"

VARIANTS = [
    ("server-own", None, None),  # danh tính server tự khai
    ("win-itunes", "<PC> <Windows;6.2(0,0);9200> <com.apple.AuthKit/1 (com.apple.iTunes/12.12.4.1)>", UA_AKD),
    ("win-akd", "<PC> <Windows;6.2(0,0);9200> <com.apple.AuthKit/1 (com.apple.akd/1.0)>", UA_AKD),
    ("pixel7", "<Pixel 7> <Android;14;UQ1A.240205.002> <com.apple.AuthKit/1 (com.apple.akd/1.0)>", UA_AKD),
    # các danh tính mà server Mac 10.12.6 đang chạy được công bố
    ("mac10.12-akd", "<MacBookPro13,3> <Mac OS X;10.12.6;16G29> <com.apple.AuthKit/1 (com.apple.akd/1.0)>",
     "akd/1.0 CFNetwork/811.5.4 Darwin/16.7.0"),
    ("mac10.12-akd-808", "<MacBookPro13,3> <Mac OS X;10.12.6;16G29> <com.apple.AuthKit/1 (com.apple.akd/1.0)>", UA_AKD),
    ("mac13-akd", "<MacBookPro13,2> <macOS;13.1;22C65> <com.apple.AuthKit/1 (com.apple.akd/1.0)>", UA_AKD),
    ("win-akd-808", "<PC> <Windows;6.2(0,0);9200> <com.apple.AuthKit/1 (com.apple.akd/1.0)>", UA_AKD),
]


def fetch_identity(base):
    """Lấy (headers_anisette, client_info, user_agent) từ server."""
    base = base.rstrip("/")
    ci, ua = None, None
    try:
        r = requests.get(base + "/v3/client_info", timeout=15, verify=False)
        if r.status_code == 200:
            j = r.json()
            ci = j.get("client_info")
            ua = j.get("user_agent")
    except Exception as e:
        return None, None, None, f"client_info lỗi: {e}"
    try:
        r = requests.get(base + "/", timeout=20, verify=False)
        if r.status_code != 200:
            return None, ci, ua, f"OTP lỗi HTTP {r.status_code}"
        h = r.json()
    except Exception as e:
        return None, ci, ua, f"OTP lỗi: {e}"
    return h, ci or h.get("X-MMe-Client-Info"), ua, None


def gsa_init(anisette, client_info, user_agent):
    user = "probe%s@icloud.com" % secrets.token_hex(5)
    cpd = {
        "bootstrap": True,
        "icscrec": True,
        "pbe": False,
        "prkgen": True,
        "svct": "iCloud",
        "X-MMe-Client-Info": client_info,
    }
    cpd.update(anisette)
    cpd["X-MMe-Client-Info"] = client_info
    body = {
        "Header": {"Version": "1.0.1"},
        "Request": {
            "cpd": cpd,
            "A2k": secrets.token_bytes(384),
            "ps": ["s2k", "s2k_fo"],
            "u": user,
            "o": "init",
        },
    }
    headers = {
        "Content-Type": "text/x-xml-plist",
        "Accept": "text/x-xml-plist",
        "User-Agent": user_agent or UA_AKD,
        "X-MMe-Client-Info": client_info,
        "X-Apple-App-Info": "com.apple.gs.xcode.auth",
        "X-Xcode-Version": "14.2 (14C18)",
        "Connection": "close",
    }
    r = requests.post(GSA, data=plistlib.dumps(body), headers=headers,
                      timeout=30, verify=False)
    out = {"http": r.status_code, "ec": None, "challenge": False,
           "ctype": r.headers.get("Content-Type", "")}
    try:
        res = plistlib.loads(r.content).get("Response", {})
        out["ec"] = (res.get("Status") or {}).get("ec")
        out["challenge"] = "sp" in res
        out["em"] = (res.get("Status") or {}).get("em")
    except Exception:
        out["snippet"] = r.content[:80].decode("utf-8", "replace").replace("\n", " ")
    return out


def verdict(res):
    http, ec = res["http"], res["ec"]
    if http == 200 and ec in (0, -20970, -20101):
        return "ACCEPTED"
    if ec == -80045:
        return "-80045 (mismatch)"
    if http in (502, 503, 504):
        return f"edge {http} (chặn danh tính?)"
    if http == 429:
        return "429 (không kết luận)"
    return f"khác (http {http} ec {ec})"


def main():
    servers = sys.argv[1:]
    if not servers:
        print("usage: gsa_matrix.py <server> [server...]   (MATRIX_OUT=file.json)")
        return 1
    rows = []
    for base in servers:
        anisette, ci_own, ua_own, err = fetch_identity(base)
        print(f"\n### {base}")
        if err:
            print("   ! " + err)
        if not anisette:
            continue
        print(f"   client_info: {ci_own}")
        print(f"   user_agent : {ua_own}")
        print(f"   device-id  : {anisette.get('X-Mme-Device-Id')}")
        print(f"   MD-RINFO   : {anisette.get('X-Apple-I-MD-RINFO')}")
        for name, ci, ua in VARIANTS:
            ci_eff = ci_own if ci is None else ci
            ua_eff = ua_own if ua is None else ua
            if not ci_eff:
                print(f"   {name:12s} -> bỏ qua (server không trả client_info)")
                continue
            try:
                res = gsa_init(anisette, ci_eff, ua_eff)
            except Exception as e:
                print(f"   {name:12s} -> lỗi mạng: {e}")
                continue
            v = verdict(res)
            print(f"   {name:12s} -> {v:26s} http={res['http']} ec={res['ec']}")
            rows.append({"server": base, "variant": name, "client_info": ci_eff,
                         "verdict": v, "http": res["http"], "ec": res["ec"]})
            time.sleep(1.5)
    out = os.environ.get("MATRIX_OUT", "gsa_matrix_result.json")
    with open(out, "w") as f:
        json.dump(rows, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
