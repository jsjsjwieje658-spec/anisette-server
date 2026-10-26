# anisette-server (chạy trên GitHub Actions + Tailscale)

> ## 🟢 Trạng thái 26/10/2026
> - Chạy được: build D OK, `GET /` trả **HTTP 200** với `X-Apple-I-MD-M` (ADI đã provision).
> - Danh tính **Windows** (`<PC> <Windows;6.2(0,0);9200> …akd…`) được Apple chấp nhận:
>   self-test `GsService2 init` trả **200 / ec=-20970**. Bản `upstream` (Mac) bị **503**.
> - Edge Apple trả **503 theo từng đợt (~50% request)** — phải retry/backoff, không phải lỗi server.
> - ⚠️ App Android (`Sideloadtool`) đặt `android:usesCleartextTraffic="false"`
>   → URL `http://100.x` **KHÔNG dùng được**, bắt buộc **HTTPS**.
>   Cần bật HTTPS trong Tailscale admin (DNS → Enable HTTPS) để có
>   `https://anisette.<tailnet>.ts.net` **ổn định qua mọi lần chạy**.
> - Nếu chưa bật: dùng URL Cloudflare trong `status/status.json` (đổi mỗi lần chạy).


Server **anisette v3** tự host, build từ source mỗi khi chưa có cache, chạy trên GitHub-hosted runner,
mở ra ngoài bằng **Tailscale** (nếu có key) và **Cloudflare quick tunnel** (luôn có).

Dùng cho tool cài IPA (`jsjsjwieje658-spec/Sideloadtool` — Android + cáp USB) hoặc SideStore/AltStore.

---

## Lấy URL

- Tab **Actions** → run mới nhất → step **“Công bố URL”** → xem *Job summary*.
- Hoặc luôn đọc được bằng máy:

  ```
  https://raw.githubusercontent.com/jsjsjwieje658-spec/anisette-server/status/status.json
  ```

Ví dụ:

```json
{
  "updated_at": "2026-10-26T10:00:00Z",
  "cloudflare": "https://xxxx-yyyy.trycloudflare.com",
  "tailscale_https": "https://anisette.tailxxxx.ts.net",
  "tailscale_http": "http://100.x.y.z:6969",
  "client_info": "<MacBookPro13,2> <macOS;13.1;22C65> <com.apple.AuthKit/1 (com.apple.akd/1.0)>",
  "user_agent": "akd/1.0 CFNetwork/808.1.4"
}
```

## Dùng trong tool Sideloadtool

1. Mở app → **Cài đặt / Settings → Anisette URL**.
2. Dán URL (ví dụ `https://xxxx.trycloudflare.com` hoặc `https://anisette.tailxxxx.ts.net`).
3. Lưu → Đăng nhập Apple ID.

Tool này đọc `/v3/client_info` để lấy `client_info` + `user_agent`, rồi lấy header từ `GET /`
(v1) — server phục vụ cả hai. Sau khi đổi server, nên đăng nhập lại để tool provision identity mới.

> **Không có xung đột VPN** như SideStore: tool này giao tiếp với iPhone qua cáp USB, nên bật
> Tailscale trên điện thoại Android **không** tranh slot VPN với gì cả.

## Bật Tailscale (khuyến nghị)

1. <https://login.tailscale.com/admin/settings/keys> → **Generate auth key**
   - Reusable: **bật** (mỗi run là một node mới)
   - Ephemeral: **bật** (node tự biến mất khi job kết thúc — không rác tailnet)
   - Expiry: 90 ngày (nhớ tạo lại)
   - (tuỳ chọn) gắn tag `tag:ci` nếu tailnet của bạn dùng ACL
2. Repo này → **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `TS_AUTHKEY`
   - Value: `tskey-auth-...`
3. (tuỳ chọn) bật HTTPS cho tailnet: admin console → **DNS → Enable HTTPS**
   → khi đó có thêm URL `https://anisette.<tailnet>.ts.net` (đẹp, không cần port, cert hợp lệ).
4. (tuỳ chọn) biến `TS_EXTRA_ARGS` nếu cần `--advertise-tags=tag:ci`.

Không có secret `TS_AUTHKEY` thì job vẫn chạy và vẫn có URL Cloudflare.

## Chạy / dừng

- **Chạy tay:** Actions → *anisette-server* → **Run workflow** (chọn `client_info`, số phút).
- **Tự động:** cron `0 */6 * * *`, mỗi job ~350 phút → gần như liên tục, nghỉ ~10 phút giữa 2 lượt.
- **Dừng:** Actions → run đang chạy → **Cancel workflow**. URL sẽ chết ngay.

## ✅ Kết quả kiểm chứng (26/10/2026)

Self-test `scripts/gsa_probe.py` gửi 1 request `GsService2 o=init` vô hại (không cần mật khẩu)
tới Apple, dùng đúng anisette headers server trả về:

| Danh tính server | Kết quả Apple | Kết luận |
|---|---|---|
| `upstream` (Mac) | **HTTP 503** (HTML) | ❌ bị chặn — ADI là Android nhưng khai Mac (issue #61) |
| `windows` (`<PC> <Windows;6.2(0,0);9200> …akd…`) | **HTTP 200, ec = -20970** | ✅ qua cửa GrandSlam (ec -20970 chỉ là "tài khoản thử không tồn tại") |
| Đối chứng: `mac-ani.jkcoxson.com` (Mac ADI thật) | HTTP 200, ec = -20970 | ✅ → IP của runner **không** phải nguyên nhân |

⇒ Repo này mặc định `client_info = windows`. Nếu sau này upstream sửa được ADI thì đổi lại `upstream`.

Lưu ý: bước `complete` (sau khi nhập mật khẩu) còn phụ thuộc Apple ID/thiết bị — có thể gặp
`-36607` (quá nhiều tài khoản trên cùng machine-id) hoặc `-23782` (macOS quá cũ). Tool đã có
logic "đốt" device-id 24h; mỗi lần job chạy mới, server sinh machine-id mới nên đỡ bị.

## `client_info` (quan trọng từ 10/2026)

Apple GrandSlam bắt đầu từ 12/10/2026 trả `-80045` / `503` khi dữ liệu anisette sinh từ **Android
CoreADI** nhưng lại khai là Mac. Server này dùng CoreADI của Apple Music APK → vì thế có tham số
chọn danh tính:

| `client_info` | Chuỗi gửi Apple | Ghi chú |
|---|---|---|
| `upstream` | `<MacBookPro13,2> <macOS;13.1;22C65> <com.apple.AuthKit/1 (com.apple.akd/1.0)>` | Bản gốc upstream |
| `windows` **(mặc định ở repo này)** | `<PC> <Windows;6.2(0,0);9200> <com.apple.AuthKit/1 (com.apple.akd/1.0)>` | Workaround đang được cộng đồng dùng |
| `windows-itunes` | `<PC> <Windows;6.2(0,0);9200> <com.apple.AuthKit/1 (com.apple.iTunes/12.12.4.1)>` | Biến thể từ server Windows ADI |

Nếu đăng nhập lỗi `-80045` / `503` → chạy lại workflow với `client_info = windows`, rồi trong tool
xoá/đổi anisette cũ và đăng nhập lại.

Link theo dõi: <https://github.com/Dadoum/anisette-v3-server/issues/61>

## Cấu trúc

```
.github/workflows/serve.yml   # build (D/dub) -> chạy server -> tailscale/cloudflare -> supervise
status/status.json            # (nhánh `status`) URL mới nhất
```

## Giới hạn & cảnh báo

- Job GitHub tối đa **6 giờ** → phải cron để nối tiếp; giữa 2 lượt có ~10 phút gián đoạn.
- Repo **public** để Actions không bị trừ quota 2000 phút/tháng của tài khoản free.
  **Đừng commit secret vào repo** — chỉ để trong Settings → Secrets.
- Chạy service thường trực trên Actions là **vùng xám** với Acceptable Use Policy của GitHub;
  tài khoản có thể bị cảnh cáo. Đừng dùng cho việc quan trọng.
- Cloudflare quick tunnel là URL **công khai ngẫu nhiên** — ai biết URL cũng lấy được OTP anisette
  của máy ảo này. Tailscale thì riêng tư. Đừng dùng Apple ID chính.
- Server không bao giờ thấy mật khẩu Apple ID: mật khẩu/2FA đi thẳng từ điện thoại tới Apple.

## Build local (nếu muốn)

```bash
sudo apt install -y ldc dub clang libssl-dev zlib1g-dev git
git clone --depth 1 https://github.com/Dadoum/anisette-v3-server /tmp/av3 && cd /tmp/av3
DC=ldc2 dub build -c static --build-mode allAtOnce -b release --compiler=ldc2
XDG_RUNTIME_DIR=/tmp ./anisette-v3-server --host 127.0.0.1 --port 6969
curl -s 127.0.0.1:6969/v3/client_info
```
