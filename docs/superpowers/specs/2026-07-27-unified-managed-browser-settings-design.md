# Hợp nhất giao diện Chrome riêng và Cookies

## Mục tiêu

Ứng dụng chỉ còn một cơ chế cookie trình duyệt chính: Chrome riêng do
`ManagedChromeSession` quản lý. Nút **Trình Duyệt** trên toolbar và tab
**Cookies** trong Cài đặt là hai điểm truy cập tới cùng một phiên Chrome, không
phải hai cách trích xuất cookie khác nhau.

## Giao diện

Tab Cookies giữ ba chế độ:

1. **Không dùng**: không cấu hình nguồn cookie dự phòng.
2. **Chrome riêng của ứng dụng**: hiển thị đường dẫn profile riêng, nút
   **Mở Chrome / Đăng nhập**, nút **Kiểm tra đăng nhập** và trạng thái phiên.
3. **File tùy chỉnh (.txt)**: giữ bộ chọn file cookie hiện tại.

Khi chọn Chrome riêng, giao diện không còn danh sách Chrome/Edge/Firefox,
không còn danh sách profile cá nhân và không hiển thị hướng dẫn DPAPI. Nút
**Trình Duyệt** trên toolbar được giữ để mở nhanh cùng phiên Chrome này.

## Luồng dữ liệu

- `MainWindow` tiếp tục sở hữu duy nhất một `ManagedChromeSession`.
- `SettingsDialog` nhận tham chiếu tới session đó từ `MainWindow`; dialog không
  tự tạo session hoặc process Chrome mới.
- **Mở Chrome / Đăng nhập** gọi `ManagedChromeSession.open_browser()`.
- Nếu profile chưa đăng nhập, Chrome được mở ở chế độ đăng nhập bình thường,
  không bật remote debugging/CDP để Google không xem đây là trình duyệt do ứng
  dụng điều khiển. Người dùng đăng nhập rồi đóng Chrome một lần.
- Khi profile đã có phiên đăng nhập, các lần mở sau mới bật CDP để tạo cookie
  lease an toàn cho tác vụ tải.
- **Kiểm tra đăng nhập** gọi API kiểm tra trạng thái của session:
  - Chrome đang mở: đọc cookie qua CDP loopback.
  - Chrome đã đóng: kiểm tra bản ghi xác thực hợp lệ trong profile riêng.
- Kiểm tra trạng thái không gọi video YouTube, không chạy yt-dlp và không tạo
  snapshot cookie cho tác vụ tải.
- Khi tải, chuỗi thử vẫn là: không cookie → ẩn danh sạch → cookie một lần.
  `managed` chỉ dùng Chrome riêng; `file` chỉ dùng file đã chọn và file lỗi
  không âm thầm fallback sang Chrome hay profile cá nhân.

## Cấu hình và migration

- Thêm khóa `cookie_source_mode` với ba giá trị `none`, `managed`, `file` để
  **Không dùng** và **Chrome riêng** không còn trùng trạng thái lưu.
- Chế độ Chrome riêng xóa các khóa profile trình duyệt cũ:
  `cookies_from_browser`, `cookies_profile`, `chrome_profile`,
  `extracted_cookies_path` và đặt `use_cookies=false`.
- Nếu settings cũ đang chọn profile trình duyệt cá nhân, khi mở dialog sẽ tự
  chuyển sang **Chrome riêng của ứng dụng**; không tiếp tục dùng profile cá nhân
  ở runtime.
- Chế độ File tùy chỉnh tiếp tục dùng `use_cookies=true` và
  `cookies_file_path` như hiện tại.
- Nút **Trình Duyệt** trên toolbar chỉ tự lưu `managed` sau khi Chrome mở thành
  công; nếu mở thất bại thì giữ nguyên mode hiện tại. Đường dẫn file tùy chỉnh
  được giữ lại khi tạm chuyển mode.

## Xử lý lỗi

- Chrome chưa cài: hiển thị thông báo cài Google Chrome.
- Profile chưa đăng nhập: hiển thị **Chưa đăng nhập YouTube** và đề nghị mở
  Chrome riêng.
- Profile/CDP bị khóa hoặc hỏng: báo lỗi rõ ràng, không treo dialog và không
  fallback sang profile Chrome cá nhân.
- Nếu Chrome đăng nhập chưa đóng, chưa cấp cookie cho tác vụ tải và hướng dẫn
  người dùng đóng đúng cửa sổ Chrome riêng trước.
- Đóng dialog không đóng Chrome; Chrome chỉ đóng theo lifecycle của app.

## Kiểm thử

- Tab Cookies không còn control chọn browser/profile hoặc thông báo DPAPI.
- Hai nút ở toolbar và dialog gọi cùng một `ManagedChromeSession`.
- Kiểm tra đăng nhập phân biệt visitor cookie với cookie xác thực hợp lệ.
- Settings cũ dùng Profile 66 được migration sang managed mode và các khóa cũ
  bị xóa khi lưu.
- File tùy chỉnh vẫn hoạt động và giữ ưu tiên cao nhất.
- Fallback ba lượt, lease cookie theo task và bảo toàn `data/browser/**` không
  thay đổi.
- Chạy targeted tests, toàn bộ pytest và `py_compile` trước khi commit code.

## Ngoài phạm vi

- Không dùng QtWebEngine.
- Không đọc hoặc sửa profile Chrome cá nhân.
- Không nâng version, build artifact, tạo tag hoặc phát hành release.
