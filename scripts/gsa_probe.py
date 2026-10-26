#!/usr/bin/env python3
"""Self-test GSA KHÔNG cần mật khẩu (có retry vì edge Apple trả 503 theo đợt).

Gửi request GsService2 `o=init` (vô hại, tài khoản không tồn tại) với anisette
headers lấy từ server, rồi đọc `ec` Apple trả:

  - HTTP 200 + ec bất kỳ (-20970/-20101/...)  -> server QUA được cửa GrandSlam
  - HTTP 503/502/504 (HTML)                   -> edge Apple đang chặn theo đợt
                                                 (thử lại sẽ pass) hoặc danh
                                                 tính bị từ chối thật (issue #61)

Apple trả 503 ngẫu nhiên ~50% số lần, nên phải thử nhiều lần mới kết luận.

Dùng: python3 gsa_probe.py <base_url> [user_thu] [so_lan_thu]
Exit code: 0 nếu PASS, 1 nếu BLOCKED.
"""
import json
import plistlib as plist
import secrets
import sys
import time
import urllib3
import requests

urllib3.disable_warnings()
GSA = "https://gsa.apple.com/grandslam/GsService2"
EDGE_STATUSES = {429, 502, 503, 504}
BACKOFF = (2, 5, 10, 15, 20, 30)


def _one(base, user, ci, anisette):
    cpd = dict(anisette)
    cpd.update({"bootstrap": True, "icscrec": True, "pbe": False,
                "prkgen": True, "svct": "iCloud"})
    body = {
        "Header": {"Version": "1.0.1"},
        "Request": {"cpd": cpd, "A2k": secrets.token_bytes(384),
                    "ps": ["s2k", "s2k_fo"], "u": user, "o": "init"},
    }
    headers = {
        "Content-Type": "text/x-xml-plist",
        "Accept": "text/x-xml-plist",
        "User-Agent": ci.get("user_agent", "akd/1.0 CFNetwork/808.1.4"),
        "X-MMe-Client-Info": ci.get("client_info", ""),
        "X-Apple-App-Info": "com.apple.gs.xcode.auth",
        "X-Xcode-Version": "14.2 (14C18)",
        "Connection": "close",
    }
    r = requests.post(GSA, data=plist.dumps(body), headers=headers,
                      timeout=30, verify=False)
    out = {"http": r.status_code, "ec": None, "em": "", "has_challenge": False}
    try:
        res = plist.loads(r.content).get("Response", {})
        st = res.get("Status") or {}
        out["ec"] = st.get("ec", 0)
        out["em"] = st.get("em", "")
        out["has_challenge"] = "sp" in res
    except Exception as exc:
        out["parse_error"] = str(exc)[:120]
        out["raw"] = r.text[:160]
    return out


def probe(base, user="probe-nonexistent-0000@icloud.com", tries=6):
    base = base.rstrip("/")
    ci = requests.get(base + "/v3/client_info", timeout=20).json()
    anisette = requests.get(base + "/", timeout=60).json()
    if "X-Apple-I-MD-M" not in anisette:
        return {"verdict": "ANISETTE_ERROR", "detail": anisette,
                "client_info": ci.get("client_info")}

    attempts = []
    for i in range(tries):
        # mỗi lần thử lấy OTP mới (OTP cũ có thể đã bị dùng trong đợt trước)
        if i:
            anisette = requests.get(base + "/", timeout=60).json()
        res = _one(base, user, ci, anisette)
        res["attempt"] = i + 1
        attempts.append(res)
        if res["http"] == 200 and isinstance(res.get("ec"), int):
            return {"verdict": "PASS", "client_info": ci.get("client_info"),
                    "user_agent": ci.get("user_agent"),
                    "http": res["http"], "ec": res["ec"], "em": res["em"],
                    "attempts_used": i + 1, "attempts": attempts}
        if res["http"] not in EDGE_STATUSES and i + 1 >= 2:
            break  # lỗi khác 5xx: retry không giúp gì
        if i + 1 < tries:
            time.sleep(BACKOFF[min(i, len(BACKOFF) - 1)])

    last = attempts[-1]
    return {"verdict": "BLOCKED", "client_info": ci.get("client_info"),
            "user_agent": ci.get("user_agent"),
            "http": last["http"], "ec": last.get("ec"), "em": last.get("em"),
            "attempts_used": len(attempts), "attempts": attempts}


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:6969"
    user = sys.argv[2] if len(sys.argv) > 2 else "probe-nonexistent-0000@icloud.com"
    tries = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    result = probe(base, user, tries)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["verdict"] == "PASS" else 1)
