# Active Context

## Current Focus

v1.0.14 là bản Smart Update đầu tiên, đồng thời sửa smoke test yt-dlp thành kiểm tra offline.

## Update migration

- v1.0.13 phát hành `YouTubeDownloaderPro-Setup-v1.0.13.exe` và `node-runtime-win-x64.pkg`; không phát hành asset `.zip`.
- Người dùng v1.0.12 chạy Setup để cài đè. Setup giữ settings, history, cookies, token, proxy, thumbnails và yt-dlp hiện có.
- Setup cài Node 24.12.0, `UpdaterLauncher.exe` ổn định và worker có version.
- Từ v1.0.14, Smart Update chỉ chọn chính xác `app-update-v2.pkg` có SHA256 digest từ GitHub Release API.
- Hai nút cập nhật vẫn độc lập; chúng chỉ dùng chung transaction, mutex, checksum, proxy, progress và log.
- Smoke test yt-dlp dùng extractor nội bộ `test:`; không truy cập YouTube hoặc tải video.
- Setup v1.0.14 có checkbox tạo Desktop shortcut và được chọn mặc định.

## Existing features

- WARP 1.1.1.1 proxy integration và đổi IP.
- Chi tiết lỗi có nút sao chép và text có thể chọn.
- Menu chuột phải mở liên kết trong trình duyệt.
