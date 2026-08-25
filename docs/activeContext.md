# Active Context

## Current Focus

v1.0.15 củng cố runtime transaction, nâng updater worker lên 2.1.0 và ghim yt-dlp 2026.07.04 cho Setup.

## Update migration

- v1.0.13 phát hành `YouTubeDownloaderPro-Setup-v1.0.13.exe` và `node-runtime-win-x64.pkg`; không phát hành asset `.zip`.
- Người dùng v1.0.12 chạy Setup để cài đè. Setup giữ settings, history, cookies, token, proxy, thumbnails và yt-dlp hiện có.
- Setup cài Node 24.12.0, `UpdaterLauncher.exe` ổn định và worker có version.
- Từ v1.0.14, Smart Update chỉ chọn chính xác `app-update-v2.pkg` có SHA256 digest từ GitHub Release API.
- Hai nút cập nhật vẫn độc lập; chúng chỉ dùng chung transaction, mutex, checksum, proxy, progress và log.
- Smoke test yt-dlp dùng extractor nội bộ `test:`; không truy cập YouTube hoặc tải video.
- Setup v1.0.14 có checkbox tạo Desktop shortcut và được chọn mặc định.
- v1.0.15 xác minh đầy đủ `node.exe` + `LICENSE`; Node 24.12.0 không đổi nên không nằm trong Smart package.
- Smart Update v1.0.15 đưa worker 2.1.0 vào package; launcher ổn định tiếp tục tự chọn worker từ manifest.
- Setup v1.0.15 chỉ nhận yt-dlp 2026.07.04 đã đối chiếu checksum chính thức, version và smoke test offline.
- Publisher retry draft bằng cách xóa sạch asset cũ và chỉ publish khi tập asset khớp chính xác.

## Existing features

- WARP 1.1.1.1 proxy integration và đổi IP.
- Chi tiết lỗi có nút sao chép và text có thể chọn.
- Menu chuột phải mở liên kết trong trình duyệt.
