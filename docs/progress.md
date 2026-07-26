# Progress

## Completed

- Hệ thống `UpdateManager` dùng chung cho app, yt-dlp và Node portable.
- Transaction có SHA256, rollback, mutex liên tiến trình và kiểm tra ZIP an toàn.
- Launcher ổn định + worker updater có version và manifest protocol v2.
- Publisher tạo draft release, xác minh từng asset rồi mới publish.
- Pipeline lấy Node 24.12.0 Windows x64 chính thức và xác minh `SHASUMS256.txt`.
- Installer migration v1.0.13 giữ nguyên dữ liệu người dùng và yt-dlp hiện có.

## Release rules

- v1.0.13: chỉ Setup `.exe` và runtime `.pkg`; không có `.zip` hoặc Smart Update package.
- v1.0.14 trở đi: Smart Update dùng `app-update-v2.pkg`.
- Smart package không chứa yt-dlp; Node và updater worker chỉ được đóng gói khi release tag của manifest trùng release hiện tại.

## Pending

- Publish release v1.0.13 sau khi kiểm thử và duyệt thủ công.
