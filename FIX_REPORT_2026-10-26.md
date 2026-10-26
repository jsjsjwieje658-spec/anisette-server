# FIX REPORT — anisette-server, 26/10/2026

**Yêu cầu:** "xem repo này https://github.com/jsjsjwieje658-spec/anisette-server fix sửa server anisette fix lỗi -80045"
(kèm log `/home/user/uploads/log.txt.json`).

**Kết luận 1 dòng:** server không hề trả `-80045` cho người dùng — **client tự gán nhãn đó cho một
`HTTP 503` của edge Apple**; và `status.json` của repo đang quảng cáo **URL tunnel đã chết
(`HTTP 530`)**. Cả hai đã được sửa (server: gate + status + phân loại; client: `v74` bên repo
`Sideloadtool`).

---

## 1. Log nói gì (đọc toàn bộ 95 dòng)

```
[anisette] Fetching headers ...                       ← LẤY HEADER TỪ SERVER, OK
[gsa] init         -> 503 HTML  (thử lại)
[gsa] init         -> 200  (có SRP challenge)          ← Apple CHẤP NHẬN danh tính
[gsa] complete     -> 200                              ← mật khẩu ĐÚNG
[2fa] hsc 409      -> Apple tự push mã 2FA; validate GET -> 200 ✅
[icloud] 2FA thành công! Đang xác thực lại để lấy token phiên đầy đủ...
[gsa] init         -> 200
[gsa] complete     -> 503 HTML ×3  (cách nhau 0,25 s)
⚠️  ec -80045: Apple từ chối danh tính anisette          ← TOOL TỰ IN, Apple không trả mã này
```

Trong cả file **không có** chuỗi `ec = -80045` nào từ Apple: mọi phản hồi lỗi đều là
`<html>503 Service Temporarily Unavailable</html>`.

## 2. Đo lại đúng server đó

| Thời điểm / nguồn | Việc | Kết quả |
|---|---|---|
| run `40319963400`, self-test của workflow | `GsService2 o=init`, Apple ID không tồn tại, cùng machine-id `0C777CE0-…` | **503, 503, 200 / ec -20970** → PASS ở lần 3 |
| run `40325948777` (code mới), gate | như trên, machine-id `55F92C5F-…` | **PASS ở lần 2** (`attempts_used=2`) |
| sandbox của tôi, cùng URL, cùng header | `gsa_probe.py --tries 6` | **503 → (backoff 2 s) → 200 / ec -20209 = PASS** |
| cùng URL lúc job bị cancel | `curl URL` | **HTTP 530** (tunnel chết) trong khi `status.json` vẫn ghi `alive` không có |

⇒ `503` = **edge Apple chặn theo đợt** (phụ thuộc cả IP người gọi). Thử lại có backoff thì qua;
thử 3 lần cách 0,25 s thì không. `-80045` thật (HTTP 200 + plist) thì **không** qua được bằng retry.

## 3. Ma trận: cái gì quyết định `-80045` / `503`

`scripts/gsa_matrix.py` — lấy header anisette của một server rồi gửi `o=init` với nhiều danh tính
trên **cùng machine-id**, Apple ID ngẫu nhiên không tồn tại (không mật khẩu, không đụng tài khoản).

| Server (ADI) | server tự khai | khai Mac 10.12.6 | khai Windows | khai Pixel 7 |
|---|---|---|---|---|
| `mac-ani.jkcoxson.com`, `ani.jkcoxson.com`, `ani.stikstore.app`, `new.ani.sidestore.io` (Mac ADI) | `<MacBookPro13,3> <Mac OS X;10.12.6;16G29> …akd…` | **PASS** | PASS (có lúc 503) | 503 |
| `ani.sidestore.app`, `anisette.crystall1ne.dev`, `ani3server.fly.dev` (ADI **Android**, khai macOS 13.1) | macOS 13.1 | **-80045** (2/2) | PASS/503 tuỳ lần | 503 |
| repo này (ADI Android + khai Windows) | `<PC> <Windows;6.2(0,0);9200> …akd…` | – | lúc PASS lúc 503 | – |

- `-80045` = **nguồn gốc machine-id lệch danh tính khai báo** (ADI Android nhưng khai Mac).
  Khớp lời tác giả `Provision`/ADI: [Dadoum/anisette-v3-server#61](https://github.com/Dadoum/anisette-v3-server/issues/61).
- Khai Android → **503 ở mọi server** ⇒ nhánh "khai Android cho khớp ADI" đã chết từ ~14/10.
- Với ADI Android, **chỉ còn danh tính Windows** và nó không ổn định → retry là bắt buộc.

## 4. Đã sửa gì trong repo này

| File | Trước | Sau |
|---|---|---|
| `scripts/gsa_probe.py` | chỉ `PASS`/`BLOCKED`, gộp 5xx với "bị chặn", `200+ec -80045` bị coi là PASS | `PASS / IDENTITY_MISMATCH / EDGE_THROTTLED / ANISETTE_ERROR`, exit 0/2/3/4, `--matrix` thử nhiều danh tính |
| `scripts/test_gsa_probe.py` | – | 9 case phân loại (không gọi mạng), 9/9 pass |
| `scripts/start_server.sh` | logic nằm rải trong YAML | `start / rotate / stop`; `rotate` xoá `device.json` + `provisioning/` để sinh machine-id mới; health 2 pha (`/v3/client_info` → `GET /` có `X-Apple-I-MD-M`) |
| `scripts/status_compose.sh`, `scripts/status_publish.py` | publish 1 lần, không có `alive` | `alive`, `expires_at`, `heartbeat_at`, `device_id`, `md_rinfo`, `gsa{verdict,ec,attempts_used}`; retry push 3 lần; nhánh **`live`** (đường cũ `status/` trả 404 vì GitHub hiểu là tên nhánh) |
| `scripts/gsa_matrix.py` | – | tái lập bảng đo ở §3 |
| `.github/workflows/serve.yml` | publish ngay, không kiểm chứng; supervisor bật lại cloudflared mà không cập nhật URL | **gate danh tính trước khi publish** (xoay machine-id ≤ 2 lần khi `EDGE_THROTTLED`, **không** xoay khi `-80045`); vá `user_agent` publish + UA của thư viện `Provision` (có guard); supervisor phát hiện URL chết → publish URL mới; heartbeat + recheck 15 phút; bước cuối `always()` đặt `alive=false`; `BUILD_REV 3→4`; `DURATION_MIN` 330 (nghỉ 30 phút để cron sau không bị xếp hàng) |
| `README.md` | tài liệu cũ + bảng Tailscale | viết lại: bảng đo, 3 lỗi khác nhau (530 / 503 / -80045), quy tắc đọc `status.json`, giới hạn |

## 5. Bằng chứng chạy thật (Actions)

- `40324926280` (code `e8b377f`): build → server → gate → tunnel → publish đều **success**;
  `status.json` có `alive:true`, `expires_at`, `url`.
- Cancel run đó → bước cuối publish **`alive:false`** (đúng lỗi cũ: URL chết vẫn được quảng cáo).
- `40325948777` (code mới, `live` branch): gate **PASS** (`attempts_used=2`),
  `https://raw.githubusercontent.com/jsjsjwieje658-spec/anisette-server/live/status.json` → **200**,
  `GET /` qua Internet có `X-Apple-I-MD-M`, `X-Mme-Device-Id = 55F92C5F-…`.
- Vá build chạy thật trên clone upstream: `clientInfo` + `user_agent` đổi đúng cho cả 4 `PATCH_MODE`;
  vá UA `Provision` đổi đúng chuỗi `akd/1.0 CFNetwork/1404.0.5 Darwin/22.3.0` → UA của mode.

## 6. Điều **chưa** kiểm chứng

- **Không** đăng nhập bằng Apple ID thật (không có mật khẩu/2FA). Mọi kết luận dựa trên `o=init`
  với Apple ID không tồn tại + log của người dùng.
- **Không** chứng minh được backoff sẽ vượt *mọi* đợt chặn; mới chứng minh được 1 chuỗi
  `503 → 200` (nhiều lần, nhiều IP).
- Việc vá UA `Provision` **chưa** đo được lợi ích (không chạy được server D trong sandbox) — chỉ
  sửa mâu thuẫn "client-info Windows + UA macOS 13".
- **Không** chữa được gốc: server vẫn dùng **ADI Android** nên danh tính Windows **không thể** ổn
  định như server Mac ADI thật. Muốn hết hẳn phải đổi nguồn ADI:
  * chạy trên `runs-on: macos-*` và dùng AOSKit/AuthKit của macOS (chưa làm, chưa đo);
  * hoặc dùng ADI của **iTunes cho Windows** (x86_64) — cần Wine/Windows runner (chưa làm, chưa đo).
- Client hiện dùng `GET /` (v1) ⇒ **mọi người biết URL dùng chung một machine-id**; chuyển sang
  `/v3/provisioning_session` (mỗi máy một danh tính) là việc tiếp theo, chưa làm.

## 7. Cách dùng

```bash
# 1) URL + trạng thái
curl -s https://raw.githubusercontent.com/jsjsjwieje658-spec/anisette-server/live/status.json | jq '{alive,url,expires_at,gsa}'

# 2) tự kiểm chứng một server bất kỳ (không cần mật khẩu)
python3 scripts/gsa_probe.py https://<server> --tries 6
#   exit 0 PASS · 2 -80045 (đổi danh tính) · 3 edge 5xx (thử lại) · 4 server chết
```

Khi gặp `503`: **chờ + thử lại**, đừng đổi server/danh tính.
Khi gặp `ec = -80045` thật: đổi danh tính/ADI — thử lại vô ích.
Khi gặp `530`: URL tunnel đã chết — đọc lại `status.json`.
