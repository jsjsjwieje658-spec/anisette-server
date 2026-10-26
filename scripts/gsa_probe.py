#!/usr/bin/env python3
"""Self-test GSA cho server anisette — KHÔNG cần mật khẩu, KHÔNG đụng tài khoản.

Gửi request GrandSlam `o=init` với một Apple ID **không tồn tại** và đúng bộ
header anisette mà server trả về, rồi phân loại câu trả lời của Apple.

Vì sao phải phân loại chứ không chỉ PASS/BLOCKED (bản cũ):

  * `HTTP 200 + ec=-80045`  → Apple **từ chối nguồn gốc machine-id**: dữ liệu
    anisette sinh từ Android CoreADI nhưng client khai Mac. Sửa bằng cách đổi
    danh tính/ADI, KHÔNG phải bằng cách thử lại.
  * `HTTP 502/503/504 (HTML)` → **edge Apple chặn theo đợt**. Đo trên runner
    26/10/2026: cùng machine-id, cùng header, lần 1–2 trả 503 HTML, lần 3 trả
    200/ec=-20970. Thử lại có tác dụng; đổi danh tính thì không.
  * `HTTP 200 + ec=-20970` → qua được cửa kiểm tra thiết bị; -20970 chỉ nghĩa
    là "tài khoản thử không tồn tại".

Đo thực tế 26/10/2026 (init, o=init, không mật khẩu) — xem README:

    server (ADI)             danh tính server khai   kết quả
    mac-ani.jkcoxson.com     Mac OS X 10.12.6        200 / -20970
    ani.stikstore.app        Mac OS X 10.12.6        200 / -20970
    new.ani.sidestore.io     Mac OS X 10.12.6        200 / -20970
    ani.sidestore.app        macOS 13.1 (ADI Android) 503 / -80045 tuỳ lần
    anisette.crystall1ne.dev macOS 13.1 (ADI Android) 503 / -80045 tuỳ lần
    ani3server.fly.dev       macOS 13.1 (ADI Android) 503 / -80045 tuỳ lần

  và khi dùng machine-id của server ADI-Android nhưng khai danh tính Mac
  10.12.6: Apple trả **-80045 trong 2/2 server, 100% số lần** → đây là lỗi
  nguồn gốc machine-id, thử lại bao nhiêu cũng vô ích.

Dùng:
    python3 scripts/gsa_probe.py <base_url> [--tries 5] [--matrix] [--json out]

Exit code:
    0 PASS              danh tính server được chấp nhận
    2 IDENTITY_MISMATCH -80045: nguồn gốc machine-id lệch danh tính khai báo
    3 EDGE_THROTTLED    toàn 5xx/429: edge chặn theo đợt, thử lại sau
    4 ANISETTE_ERROR    server không trả được X-Apple-I-MD-M
"""
import argparse
import json
import plistlib as plist
import secrets
import sys
import time

import requests
import urllib3

urllib3.disable_warnings()

GSA = "https://gsa.apple.com/grandslam/GsService2"
EDGE_STATUSES = {429, 502, 503, 504}
# ec nghĩa là "machine-id/OTP không hợp lệ với danh tính khai báo" (Apple từ chối
# thiết bị, chưa hề kiểm tra mật khẩu) — KHÔNG phải pass.
IDENTITY_REJECT_EC = {-80045, -80009, -80010, -29004, -80044}
BACKOFF = (2, 5, 10, 15, 20, 30)
DEFAULT_USER = "probe-nonexistent-0000@icloud.com"
DEFAULT_UA = "akd/1.0 CFNetwork/808.1.4"

# Các danh tính dùng cho chẩn đoán khi danh tính của server bị từ chối.
# "name": (client_info, user_agent | None = dùng UA server trả)
DIAGNOSTIC_VARIANTS = {
    "win-akd": ("<PC> <Windows;6.2(0,0);9200> <com.apple.AuthKit/1 (com.apple.akd/1.0)>",
                "akd/1.0 CFNetwork/808.1.4"),
    "win-itunes": ("<PC> <Windows;6.2(0,0);9200> <com.apple.AuthKit/1 (com.apple.iTunes/12.12.4.1)>",
                   "akd/1.0 CFNetwork/808.1.4"),
    "mac10.12": ("<MacBookPro13,3> <Mac OS X;10.12.6;16G29> <com.apple.AuthKit/1 (com.apple.akd/1.0)>",
                 "akd/1.0 CFNetwork/811.5.4 Darwin/16.7.0"),
    "pixel7-android": ("<Pixel 7> <Android;14;UQ1A.240205.002> <com.apple.AuthKit/1 (com.apple.akd/1.0)>",
                       "akd/1.0 CFNetwork/808.1.4"),
}


class ProbeError(Exception):
    pass


def fetch(base, timeout=60):
    """Lấy (client_info, user_agent, anisette_headers) từ server."""
    base = base.rstrip("/")
    try:
        info = requests.get(base + "/v3/client_info", timeout=20).json()
    except Exception as exc:  # server cũ không có /v3/client_info
        info = {}
        info_err = str(exc)[:120]
    else:
        info_err = None
    try:
        anisette = requests.get(base + "/", timeout=timeout).json()
    except Exception as exc:
        raise ProbeError(f"GET / thất bại: {exc}")
    if "X-Apple-I-MD-M" not in anisette:
        raise ProbeError(f"GET / không có X-Apple-I-MD-M: {str(anisette)[:200]}")
    return info, anisette, info_err


def one_init(user, client_info, user_agent, anisette):
    """Một request GsService2 `o=init` (không mật khẩu)."""
    cpd = dict(anisette)
    cpd.update({"bootstrap": True, "icscrec": True, "pbe": False,
                "prkgen": True, "svct": "iCloud", "X-MMe-Client-Info": client_info})
    body = {
        "Header": {"Version": "1.0.1"},
        "Request": {"cpd": cpd, "A2k": secrets.token_bytes(384),
                    "ps": ["s2k", "s2k_fo"], "u": user, "o": "init"},
    }
    headers = {
        "Content-Type": "text/x-xml-plist",
        "Accept": "text/x-xml-plist",
        "User-Agent": user_agent or DEFAULT_UA,
        "X-MMe-Client-Info": client_info,
        "X-Apple-App-Info": "com.apple.gs.xcode.auth",
        "X-Xcode-Version": "14.2 (14C18)",
        "Connection": "close",
    }
    r = requests.post(GSA, data=plist.dumps(body), headers=headers,
                      timeout=30, verify=False)
    out = {"http": r.status_code, "ec": None, "em": "", "has_challenge": False}
    try:
        res = plist.loads(r.content).get("Response", {})
        status = res.get("Status") or {}
        out["ec"] = status.get("ec", 0)
        out["em"] = status.get("em", "")
        out["has_challenge"] = "sp" in res
    except Exception as exc:
        out["parse_error"] = str(exc)[:100]
        out["raw"] = r.text[:120].replace("\n", " ")
    return out


def classify(attempts):
    """Phân loại một chuỗi lần thử của CÙNG một danh tính."""
    for a in attempts:
        if (a["http"] == 200 and isinstance(a.get("ec"), int)
                and a["ec"] not in IDENTITY_REJECT_EC):
            return "PASS"
    if any(a.get("ec") in IDENTITY_REJECT_EC for a in attempts):
        return "IDENTITY_MISMATCH"
    if all(a["http"] in EDGE_STATUSES for a in attempts):
        return "EDGE_THROTTLED"
    if all(a["http"] == 0 for a in attempts):
        return "ANISETTE_ERROR"
    return "UNKNOWN"


def run_variant(base, user, client_info, user_agent, tries, anisette=None,
                refresh_between=True):
    attempts = []
    for i in range(tries):
        if anisette is None or (i and refresh_between):
            try:
                _, anisette, _ = fetch(base)
            except ProbeError as exc:
                attempts.append({"http": 0, "ec": None, "error": str(exc)[:160],
                                 "attempt": i + 1})
                break
        res = one_init(user, client_info, user_agent, anisette)
        res["attempt"] = i + 1
        attempts.append(res)
        if (res["http"] == 200 and isinstance(res.get("ec"), int)
                and res["ec"] not in IDENTITY_REJECT_EC):
            break
        if res["http"] not in EDGE_STATUSES:
            break  # lỗi khác 5xx → thử lại không giúp gì
        if i + 1 < tries:
            time.sleep(BACKOFF[min(i, len(BACKOFF) - 1)])
    return {"verdict": classify(attempts), "attempts": attempts,
            "http": attempts[-1]["http"], "ec": attempts[-1].get("ec")}


def probe(base, user=DEFAULT_USER, tries=5, matrix=False):
    base = base.rstrip("/")
    try:
        info, anisette, info_err = fetch(base)
    except ProbeError as exc:
        return {"verdict": "ANISETTE_ERROR", "server": base, "detail": str(exc)}

    client_info = (info.get("client_info") or anisette.get("X-MMe-Client-Info")
                   or anisette.get("X-Mme-Client-Info"))
    user_agent = info.get("user_agent") or DEFAULT_UA
    result = {
        "server": base,
        "client_info": client_info,
        "user_agent": user_agent,
        "device_id": anisette.get("X-Mme-Device-Id"),
        "md_rinfo": anisette.get("X-Apple-I-MD-RINFO"),
        "client_info_endpoint": None if info_err else "ok",
    }
    if info_err:
        result["client_info_error"] = info_err
    if not client_info:
        result.update({"verdict": "ANISETTE_ERROR",
                       "detail": "server không trả client_info"})
        return result

    own = run_variant(base, user, client_info, user_agent, tries, anisette)
    result.update({"verdict": own["verdict"], "http": own["http"],
                   "ec": own["ec"], "attempts": own["attempts"],
                   "attempts_used": len(own["attempts"])})

    # Danh tính server bị từ chối / không kết luận được → thử vài danh tính
    # khác trên CÙNG machine-id để biết là lỗi nguồn gốc hay lỗi danh tính.
    if matrix and own["verdict"] != "PASS":
        diag = {}
        for name, (ci, ua) in DIAGNOSTIC_VARIANTS.items():
            if ci == client_info:
                continue
            diag[name] = run_variant(base, user, ci, ua, 2)
            time.sleep(1)
        result["diagnostics"] = diag
        passed = [n for n, d in diag.items() if d["verdict"] == "PASS"]
        if passed:
            result["suggested_identity"] = passed[0]
    return result


EXIT_CODES = {"PASS": 0, "IDENTITY_MISMATCH": 2, "EDGE_THROTTLED": 3,
              "ANISETTE_ERROR": 4, "UNKNOWN": 5}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("base", nargs="?", default="http://127.0.0.1:6969")
    ap.add_argument("--user", default=DEFAULT_USER)
    ap.add_argument("--tries", type=int, default=5)
    ap.add_argument("--matrix", action="store_true",
                    help="khi danh tính server bị từ chối, thử thêm vài danh "
                         "tính khác để tìm ra danh tính dùng được")
    ap.add_argument("--json", help="ghi kết quả ra file")
    args = ap.parse_args(argv)

    result = probe(args.base, args.user, args.tries, args.matrix)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.json:
        with open(args.json, "w") as fh:
            fh.write(text)
    print(text)
    return EXIT_CODES.get(result["verdict"], 5)


if __name__ == "__main__":
    sys.exit(main())
