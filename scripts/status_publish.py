#!/usr/bin/env python3
"""Đẩy status.json + url.txt lên nhánh `status` của repo này.

Vì sao cần script riêng: URL của Cloudflare *quick tunnel* đổi mỗi lần
cloudflared khởi động lại, và job chết là URL chết ngay. Bản cũ chỉ đẩy status
MỘT lần lúc bắt đầu, nên status.json vẫn quảng cáo một URL đã chết (đo được
26/10/2026: status.json ghi URL của run 40319963400, curl URL đó trả HTTP 530
sau khi job bị cancel). Client đọc status.json rồi báo lỗi "server bị Apple từ
chối" — sai nguyên nhân.

Script này được gọi ở 3 chỗ trong workflow:
  * sau khi có URL        (alive=true, kèm expires_at)
  * mỗi khi URL đổi / heartbeat
  * ở bước cuối (always)  (alive=false) → client biết URL đã chết

Dùng:
    python3 scripts/status_publish.py status.json --url https://x.trycloudflare.com
    python3 scripts/status_publish.py status.json --alive false
"""
import argparse
import json
import os
import subprocess
import sys
import time

BRANCH = "live"


def git(*args, check=True):
    res = subprocess.run(["git", *args], capture_output=True, text=True)
    if check and res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {res.stderr.strip()[:400]}")
    return res


def read_json(path):
    with open(path) as fh:
        return json.load(fh)


def publish(status_path, url=None, alive=None, push=True):
    data = read_json(status_path)
    # giữ URL của lần publish trước nếu lần này không truyền --url
    # (bước "job kết thúc" chỉ cần đổi alive=false, không được xoá URL)
    prev_path = os.path.join("status", "status.json")
    if not url and not data.get("url") and os.path.exists(prev_path):
        try:
            prev = read_json(prev_path)
            url = prev.get("url")
            data.setdefault("expires_at", prev.get("expires_at"))
            data.setdefault("identity_mode", prev.get("identity_mode"))
        except Exception:
            pass
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    data["heartbeat_at"] = now
    if url:
        data["url"] = url
        data["anisette_url"] = url
    if alive is not None:
        data["alive"] = alive
    if not data.get("updated_at"):
        data["updated_at"] = now

    # Ghi ở GỐC repo, trên nhánh `live` → URL raw không bị nhập nhằng:
    #   raw.githubusercontent.com/<owner>/<repo>/live/status.json
    # (đặt ở thư mục `status/` trên nhánh `status` thì raw trả 404 vì GitHub
    #  hiểu "status/status.json" là tên nhánh — đo được 26/10/2026)
    with open("status.json", "w") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    if data.get("url"):
        with open("url.txt", "w") as fh:
            fh.write(data["url"] + "\n")

    if not push:
        print(f"[status] (local only) alive={data.get('alive')} url={data.get('url')}")
        return 0

    git("config", "user.name", "anisette-bot")
    git("config", "user.email", "anisette-bot@users.noreply.github.com")
    git("checkout", "-q", "-B", BRANCH)
    git("add", "-f", "status.json", "url.txt")
    commit = git("commit", "-qm", f"status: {now} alive={data.get('alive')}", check=False)
    if commit.returncode != 0 and "nothing to commit" not in (commit.stdout + commit.stderr):
        print(f"[status] commit: {commit.stdout.strip()} {commit.stderr.strip()[:200]}")

    last = ""
    for attempt in range(1, 4):
        res = git("push", "-q", "-f", "origin", BRANCH, check=False)
        if res.returncode == 0:
            print(f"[status] pushed (lần {attempt}): alive={data.get('alive')} "
                  f"url={data.get('url')}")
            return 0
        last = (res.stderr or res.stdout).strip()[:300]
        time.sleep(3 * attempt)
    print(f"[status] PUSH FAILED: {last}", file=sys.stderr)
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("status_json")
    ap.add_argument("--url", default=None)
    ap.add_argument("--alive", choices=["true", "false"], default=None)
    ap.add_argument("--no-push", action="store_true")
    args = ap.parse_args(argv)
    alive = None if args.alive is None else args.alive == "true"
    return publish(args.status_json, args.url, alive, push=not args.no_push)


if __name__ == "__main__":
    sys.exit(main())
