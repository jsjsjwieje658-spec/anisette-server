#!/usr/bin/env python3
"""Test phân loại của gsa_probe.py (không gọi mạng).

Chạy: python3 scripts/test_gsa_probe.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gsa_probe  # noqa: E402


def attempts(*pairs):
    return [{"http": h, "ec": e} for h, e in pairs]


CASES = [
    # (mô tả, attempts, verdict mong đợi)
    ("200 + tài khoản thử không tồn tại", attempts((200, -20970)), "PASS"),
    ("200 + tài khoản bị khoá (vẫn qua cửa thiết bị)", attempts((200, -20209)), "PASS"),
    ("200 + -80045: nguồn gốc machine-id bị từ chối",
     attempts((200, -80045)), "IDENTITY_MISMATCH"),
    ("503 rồi 200: edge chặn theo đợt, thử lại được",
     attempts((503, None), (200, -20970)), "PASS"),
    ("503 cả 3 lần: edge đang chặn theo đợt",
     attempts((503, None), (503, None), (503, None)), "EDGE_THROTTLED"),
    ("503 rồi -80045: lỗi danh tính, không phải lỗi tạm thời",
     attempts((503, None), (200, -80045)), "IDENTITY_MISMATCH"),
    ("-80010 thiếu OTP: vẫn là danh tính/OTP không hợp lệ",
     attempts((200, -80010)), "IDENTITY_MISMATCH"),
    ("server chết (http 0)", attempts((0, None)), "ANISETTE_ERROR"),
    ("429 là edge, không kết luận", attempts((429, None)), "EDGE_THROTTLED"),
]


def main():
    failed = 0
    for desc, tries, expected in CASES:
        got = gsa_probe.classify(tries)
        ok = got == expected
        failed += 0 if ok else 1
        print(f"{'✅' if ok else '❌'} {desc}: {got} (mong đợi {expected})")
    total = len(CASES)
    print(f"\n{total - failed}/{total} pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
