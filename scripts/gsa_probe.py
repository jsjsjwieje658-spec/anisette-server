#!/usr/bin/env python3
"""Self-test GSA KHÔNG cần mật khẩu.

Gửi đúng một request GsService2 `o=init` (vô hại) với anisette headers lấy từ
server. Đọc `ec` Apple trả về:

  - ec = -20970 / -20101 / bất kỳ ec nào  -> server QUA được cửa GrandSlam
                                             (chỉ là tài khoản thử không tồn tại)
  - HTTP 503 (HTML)                       -> Apple chặn danh tính (Android ADI
                                             nhưng khai Mac/Windows) — issue #61
  - HTTP 200 + parse lỗi                  -> response lạ, xem raw

Dùng: python3 gsa_probe.py <base_url> [user_thu]
"""
import json
import plistlib as plist
import secrets
import sys
import urllib3
import requests

urllib3.disable_warnings()
GSA = "https://gsa.apple.com/grandslam/GsService2"


def probe(base, user="probe-nonexistent-0000@icloud.com"):
    base = base.rstrip("/")
    ci = requests.get(base + "/v3/client_info", timeout=20).json()
    anisette = requests.get(base + "/", timeout=60).json()
    if "X-Apple-I-MD-M" not in anisette:
        return {"ok": False, "stage": "anisette", "detail": anisette}

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
    out = {"ok": True, "http": r.status_code, "ec": None, "em": "",
           "has_challenge": False, "client_info": ci.get("client_info")}
    try:
        res = plist.loads(r.content).get("Response", {})
        st = res.get("Status") or {}
        out["ec"] = st.get("ec", 0)
        out["em"] = st.get("em", "")
        out["has_challenge"] = "sp" in res
    except Exception as exc:  # HTML của Apple
        out["parse_error"] = str(exc)[:120]
        out["raw"] = r.text[:200]
    out["verdict"] = ("PASS" if out["http"] == 200 and isinstance(out["ec"], int)
                      else "BLOCKED")
    return out


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:6969"
    user = sys.argv[2] if len(sys.argv) > 2 else "probe-nonexistent-0000@icloud.com"
    print(json.dumps(probe(base, user), ensure_ascii=False, indent=2))
