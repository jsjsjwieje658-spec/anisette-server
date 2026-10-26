# anisette-server (GitHub Actions + Cloudflare Tunnel)

Server **anisette-v3** tự host, build từ source upstream (`Dadoum/anisette-v3-server`) trên
GitHub-hosted runner, mở ra ngoài bằng **Cloudflare quick tunnel** (HTTPS, không cần cấu hình).

Dùng cho tool cài IPA (`jsjsjwieje658-spec/Sideloadtool` — Android + cáp USB) hoặc SideStore/AltStore.

---

## 🟢 Lấy URL hiện tại

```bash
curl -s https://raw.githubusercontent.com/jsjsjwieje658-spec/anisette-server/live/status.json | jq .
```

`status.json` (nhánh `live`, file ở gốc repo) — đọc **cả** `alive` và `expires_at`, đừng chỉ đọc `url`:

```json
{
 "updated_at": "2026-10-26T12:09:02Z",
 "heartbeat_at": "2026-10-26T12:09:02Z",
 "alive": true,
 "run_id": "40319963400",
 "url": "https://immediately-amazing-promises-exports.trycloudflare.com",
 "expires_at": "2026-10-26T17:39:00Z",
 "identity_mode": "windows",
 "client_info": "<PC> <Windows;6.2(0,0);9200> <com.apple.AuthKit/1 (com.apple.akd/1.0)>",
 "user_agent": "akd/1.0 CFNetwork/808.1.4",
 "device_id": "0C777CE0-F05F-4D5C-9915-65DF93A93D89",
 "md_rinfo": "17106176",
 "gsa": { "verdict": "PASS", "http": 200, "ec": -20970, "checked_at": "..." }
}
```

Quy tắc cho client:

| Trường | Ý nghĩa |
|---|---|
| `alive=false` | **URL đã chết** (job kết thúc/bị cancel). Đừng dùng, đọc lại file. |
| `now > expires_at` | Job đã hết hạn từ lâu → coi như chết dù `alive` còn `true`. |
| `gsa.verdict` | `PASS` = Apple chấp nhận danh tính; `EDGE_THROTTLED` = Apple đang chặn theo đợt (thử lại có tác dụng); `IDENTITY_MISMATCH` = `-80045` thật. |
| `client_info` / `user_agent` | **Phải gửi đúng cặp này** trong `X-MMe-Client-Info` và `User-Agent` của mọi request GSA. |

---

> ⚠️ **Đường dẫn cũ đã bỏ:** `.../status/status.json` (nhánh `status`, thư mục `status/`) trả **404**
> vì GitHub hiểu `status/status.json` là *tên nhánh*. Dùng `.../live/status.json` (nhánh `live`,
> file ở gốc repo) hoặc đọc qua API:
> `https://api.github.com/repos/jsjsjwieje658-spec/anisette-server/contents/status.json?ref=live`.

## ⚠️ Ba lỗi khác nhau, đừng gộp làm một

Đo trên server này + các server công khai ngày **26/10/2026** (`o=init`, Apple ID không tồn tại,
không gửi mật khẩu):

| Hiện tượng | Nguyên nhân thật | Chữa bằng |
|---|---|---|
| `HTTP 530` / không kết nối được | **Tunnel/Cloudflare chết** (job bị cancel). Không liên quan Apple. | Đọc lại `status.json`, sang URL mới |
| `HTTP 503` + HTML `Service Temporarily Unavailable` | **Edge Apple chặn theo đợt.** Cùng machine-id, cùng header: lần 1–2 → 503, lần 3 → 200/ec `-20970` (đo được trong run `40319963400`, bước *Self-test GSA*) | **Retry với backoff** (2→5→10→15→20→30 s) trên socket mới |
| `ec = -80045` (HTTP 200, plist) | **Nguồn gốc machine-id lệch danh tính khai báo**: ADI Android sinh machine-id nhưng client khai Mac | Đổi danh tính/ADI. Retry **vô ích** |

Đo cụ thể cho `-80045` (dùng machine-id của server ADI-Android, khai danh tính Mac 10.12.6):
`ani.sidestore.app` → `-80045`, `anisette.crystall1ne.dev` → `-80045` (**2/2 server, 100 % số lần**);
khai Windows (`<PC> <Windows;6.2(0,0);9200> …`) trên cùng machine-id → lúc được (`ec -20970`) lúc 503.
Khai Android/Pixel 7 → **503 ở mọi server đã thử**.

⇒ Với ADI Android (thứ upstream dùng), chỉ còn **danh tính Windows** là khả thi, và nó *không ổn định*.
Đây là giới hạn của cách làm, không phải tham số sai — xem [Dadoum/anisette-v3-server#61](https://github.com/Dadoum/anisette-v3-server/issues/61)
(chính tác giả Provision/ADI viết: *"Apple does not want us to lie on the device used to generate
Anisette data… Android device can't access grandslam"*).

---

## Danh tính (`client_info`) — tham số workflow

| `PATCH_MODE` | Chuỗi gửi Apple | Trạng thái |
|---|---|---|
| `windows` **(mặc định)** | `<PC> <Windows;6.2(0,0);9200> <com.apple.AuthKit/1 (com.apple.akd/1.0)>` + UA `akd/1.0 CFNetwork/808.1.4` | Khả thi nhất với ADI Android; hay gặp 503 theo đợt |
| `windows-itunes` | `<PC> <Windows;6.2(0,0);9200> <com.apple.AuthKit/1 (com.apple.iTunes/12.12.4.1)>` | Biến thể; đo được lúc PASS lúc 503 |
| `upstream` | `<MacBookPro13,2> <macOS;13.1;22C65> …` | ❌ ADI Android + khai Mac = `-80045`/503 |
| `mac10.12-diagnostic` | `<MacBookPro13,3> <Mac OS X;10.12.6;16G29> …` | ⚠️ **chỉ để đo**: khai danh tính của server Mac thật trên machine-id Android → `-80045` 100 % |

Trên máy Mac ADI thật (ví dụ `mac-ani.jkcoxson.com`, `ani.stikstore.app`, `new.ani.sidestore.io`)
cả ba server này đều khai `<MacBookPro13,3> <Mac OS X;10.12.6;16G29> <com.apple.AuthKit/1 (com.apple.akd/1.0)>`
và được Apple chấp nhận (`ec -20970`) khi khai **đúng** chuỗi đó — tức muốn hết hẳn lỗi thì phải
đổi **nguồn ADI** (Mac/Windows thật), không phải đổi chuỗi. Repo này chưa làm được điều đó trên
`ubuntu-latest`; xem §"Giới hạn".

---

## Workflow làm gì (bản 26/10/2026)

1. `Cache binary + gói dub + lib Apple` — cache **không** chứa `device.json`, nên mỗi run ADI
   provision một machine-id mới (kiểm chứng trong log: `Creating machine... → Provisioning done!`).
2. `Build anisette-v3-server` — vá `enum clientInfo`, vá `user_agent` trả ở `/v3/client_info`
   (phải khớp nhau), và vá `User-Agent` của **thư viện Provision** (`akd/1.0 CFNetwork/1404.0.5
   Darwin/22.3.0` → UA của mode) để lúc provision ADI không khai macOS trong khi client-info khai
   Windows. Bản vá chạy có guard: không tìm thấy file thì chỉ cảnh báo.
3. `Chạy server + health check` (`scripts/start_server.sh`) — chờ `/v3/client_info`, rồi chờ
   `GET /` có `X-Apple-I-MD-M` (ADI đã provision).
4. `Kiểm chứng danh tính với Apple` (`scripts/gsa_probe.py`) — gate **trước khi publish**:
   - `PASS` → publish.
   - `EDGE_THROTTLED` → xoay machine-id tối đa 2 lần (`start_server.sh rotate`, xoá `device.json`
     + `provisioning/`) rồi thử lại.
   - `IDENTITY_MISMATCH` (`-80045`) → **không xoay** (vô ích), báo lỗi rõ nguyên nhân.
   - `--matrix`: khi danh tính server bị từ chối, thử thêm vài danh tính khác trên cùng machine-id
     để biết là lỗi nguồn gốc hay lỗi chuỗi.
5. `Cloudflare quick tunnel` → `Công bố URL + trạng thái` (`scripts/status_compose.sh` +
   `scripts/status_publish.py`).
6. `Giữ server sống + heartbeat` — mỗi phút: server sống? tunnel sống? Nếu URL chết và
   cloudflared sinh URL mới → **publish lại**. Mỗi 15 phút chạy lại gate và cập nhật `status.json`.
7. Bước cuối (`always`) đặt `alive=false` — đây là lỗi của bản cũ: `status.json` vẫn quảng cáo URL
   của job đã cancel, client gọi vào → 530/503 rồi báo `-80045` sai.

### Script

```
scripts/gsa_probe.py          # phân loại PASS / IDENTITY_MISMATCH / EDGE_THROTTLED / ANISETTE_ERROR
scripts/gsa_matrix.py         # đo 4-8 danh tính trên CÙNG machine-id của server (ra bảng ở README)
scripts/test_gsa_probe.py     # test phân loại (không gọi mạng) — 9 case
scripts/start_server.sh       # start | rotate | stop + health/provision check
scripts/status_compose.sh     # ghép status.json
scripts/status_publish.py     # đẩy status.json + url.txt lên nhánh live
```

```bash
python3 scripts/test_gsa_probe.py                 # 9/9 pass
python3 scripts/gsa_probe.py http://127.0.0.1:6969 --tries 4 --matrix
python3 scripts/gsa_matrix.py https://ani.jkcoxson.com https://ani.sidestore.app
# exit 0 PASS · 2 -80045 · 3 edge 5xx · 4 server không sinh được anisette
```

---

## Dùng trong Sideloadtool

1. App → **Cài đặt → Anisette URL** → dán `url` trong `status.json`.
2. Tool đọc `/v3/client_info` (client_info + user_agent) rồi lấy header từ `GET /` (v1).
3. Đổi server thì đăng nhập lại để provision identity mới.

Client **phải** retry 5xx với backoff và **không** được báo `-80045` cho lỗi 503 (xem
`FIX_REPORT_v74.md` bên repo Sideloadtool).

---

## Giới hạn & cảnh báo (đọc trước khi tin)

- **Không thể chữa `-80045` bằng đổi chuỗi `client_info`.** Với ADI Android, chuỗi Mac bị Apple
  từ chối; chuỗi Android bị 503; chuỗi Windows là đường duy nhất còn lại và nó không ổn định.
  Muốn chắc chắn phải dùng anisette sinh từ **máy Mac/Windows thật** (ví dụ chạy trên
  `runs-on: macos-*` với ADI gốc, hoặc dùng Windows ADI của iTunes) — repo này **chưa** làm, và
  chưa có bằng chứng đo được trong repo.
- **URL đổi mỗi lần workflow chạy** (cron 6 giờ/lần) và **chết ngay khi job cancel**. Muốn URL cố
  định: Cloudflare named tunnel (cần domain) — xem cuối file.
- Job GitHub tối đa 6 giờ → cron `0 */6 * * *`, `DURATION_MIN` mặc định 330 → nghỉ ~30 phút giữa
  hai lượt (nghỉ dài hơn bản cũ 320/340 để chắc chắn cron kế tiếp không bị xếp hàng).
- Nếu một run khác đang chạy, run mới **xếp hàng** (`concurrency`, `cancel-in-progress: false`)
  → hãy đợi hoặc cancel run cũ trước khi bấm Run workflow.
- Cloudflare quick tunnel là URL công khai ngẫu nhiên: ai biết URL cũng lấy được OTP anisette của
  máy ảo này. **Đừng dùng Apple ID chính.**
- Server không bao giờ thấy mật khẩu Apple ID: mật khẩu/2FA đi thẳng từ điện thoại tới Apple.
- Chạy service thường trực trên Actions là vùng xám với Acceptable Use Policy của GitHub.
- Repo public để Actions không trừ quota. **Đừng commit secret.**

---

## Kết quả kiểm chứng

| Ngày | Việc | Kết quả |
|---|---|---|
| 26/10/2026 | Self-test run `40319963400` (danh tính `windows`) | lần 1–2: `503` HTML · lần 3: `200 / ec -20970` → **PASS** |
| 26/10/2026 | Gate trong run `40325948777` (code mới) | `PASS` ở lần thử **2** (`gsa.attempts_used=2`) — retry có tác dụng |
| 26/10/2026 | Gọi server đang chạy từ **một IP khác** (sandbox) | `503` → (backoff 2 s) → `200 / ec -20209` = **PASS**; cùng URL, cùng header, cùng machine-id |
| 26/10/2026 | Cancel run → bước cuối `always()` | `status.json` chuyển `alive:false` (bản cũ vẫn quảng cáo URL chết → client báo `-80045` sai) |
| 26/10/2026 | `raw.githubusercontent.com/.../live/status.json` | **200** (đường cũ `.../status/status.json` trả 404 — xem ghi chú dưới) |
| 26/10/2026 | `status.json` sau khi run bị cancel | URL trả **HTTP 530** (tunnel chết) → client báo sai `-80045` |
| 26/10/2026 | Matrix (`tools/gsa_matrix.py`) trên 8 server công khai | xem bảng §"Ba lỗi khác nhau" |
| 26/10/2026 | `scripts/test_gsa_probe.py` | 9/9 case pass |

---

## Build / chạy local

```bash
sudo apt install -y ldc dub clang libssl-dev zlib1g-dev git libplist-2.0-3
git clone --depth 1 https://github.com/Dadoum/anisette-v3-server /tmp/av3 && cd /tmp/av3
DC=ldc2 dub build -c static --build-mode allAtOnce -b release --compiler=ldc2
BIN=/tmp/av3/anisette-v3-server ADI=$HOME/.config/anisette-v3 PORT=6969 \
  bash scripts/start_server.sh start
python3 scripts/gsa_probe.py http://127.0.0.1:6969 --tries 4
```

## Cấu trúc

```
.github/workflows/serve.yml   # build → gate danh tính → tunnel → status → supervise
scripts/                      # gsa_probe, start_server, status_compose, status_publish, test
status.json                   # (nhánh `live`) URL + alive + expires_at + kết quả gate
```

## Muốn URL cố định? (Cloudflare named tunnel)

1. Cloudflare Dashboard → **Zero Trust → Networks → Tunnels → Create tunnel** → lấy `TUNNEL_TOKEN`.
2. Repo → **Settings → Secrets and variables → Actions** → thêm `CF_TUNNEL_TOKEN`.
3. Public Hostname: `anisette.tenmiencuaban.com` → service `http://127.0.0.1:6969`.
4. Thay bước Cloudflare trong `serve.yml`:

```yaml
nohup /tmp/cloudflared tunnel --no-autoupdate run \
  --token "${{ secrets.CF_TUNNEL_TOKEN }}" > /tmp/anisette/cf.log 2>&1 &
```

Khi đó `url.txt` luôn là `https://anisette.tenmiencuaban.com` — dán vào tool **một lần**.

## (Đã bỏ) Tailscale

Bản cũ mở thêm đường Tailscale; đã bỏ vì tool chạy trên Android cần VPN slot và URL ts.net hay bị
tắt. Nếu cần lại: tạo auth key (reusable + ephemeral), thêm secret `TS_AUTHKEY`, thêm bước
`tailscale up`.
