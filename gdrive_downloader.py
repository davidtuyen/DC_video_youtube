import os
import io
import re
import json
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError
import traceback
def extract_file_id_from_google_drive_url(url):
    if not url or not isinstance(url, str):
        return None
    
    match1 = re.search(r'/file/d/([a-zA-Z0-9_-]+)', url)
    if match1:
        return match1.group(1)
    
    match2 = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', url)
    if match2:
        return match2.group(1)
        
    match3 = re.search(r'/([a-zA-Z0-9_-]{20,})[/?]', url) 
    if match3:
        potential_id = match3.group(1)
        if len(potential_id) > 25 and len(potential_id) < 40 : 
            if not any(kw in potential_id for kw in ['http', 'folders', 'view', 'edit', 'sharing', 'usp']):
                return potential_id
    return None

def extract_folder_id_from_google_drive_url(url: str) -> str | None:
    """Trích xuất ID từ một URL thư mục Google Drive."""
    if not url or not isinstance(url, str):
        return None
    # Pattern cho URL dạng /folders/ID
    match = re.search(r'/folders/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    return None

def list_files_in_drive_folder(drive_service, folder_id: str, status_callback=print):
    """
    Liệt kê tất cả các file trong một thư mục Google Drive.
    Hàm này không đệ quy (chỉ liệt kê ở cấp đầu tiên).
    Trả về một danh sách các dictionary, mỗi dict chứa 'id' và 'name' của file.
    """
    files_in_folder = []
    page_token = None
    try:
        while True:
            # Truy vấn API để tìm các mục có folder_id là parent
            # và không phải là thư mục (mimeType != 'application/vnd.google-apps.folder')
            # và không nằm trong thùng rác
            response = drive_service.files().list(
                q=f"'{folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false",
                spaces='drive',
                fields='nextPageToken, files(id, name)',
                pageToken=page_token
            ).execute()

            for file_item in response.get('files', []):
                files_in_folder.append({
                    'id': file_item.get('id'),
                    'name': file_item.get('name')
                })
            
            page_token = response.get('nextPageToken', None)
            if page_token is None:
                break
        
        status_callback("message", f"[DriveLister] Tìm thấy {len(files_in_folder)} file trong thư mục ID: {folder_id}")
        return files_in_folder, None
    
    except HttpError as error:
        error_message = f"Lỗi API khi liệt kê file trong thư mục '{folder_id}': {error}"
        status_callback("message", f"[DriveLister-ERROR] {error_message}")
        return [], error_message
    except Exception as e:
        error_message = f"Lỗi không xác định khi liệt kê file trong thư mục '{folder_id}': {e}"
        status_callback("message", f"[DriveLister-ERROR] {error_message}")
        return [], error_message


def download_file_from_drive(drive_service, file_id, download_dir, status_callback=print):
    """
    Tải một file từ Google Drive bằng file_id, lưu vào download_dir.
    Giữ nguyên tên file gốc. Xử lý export cho Google Workspace files.
    status_callback is expected to handle (msg_type, data)
    """
    try:
        file_metadata = drive_service.files().get(fileId=file_id, fields="id, name, mimeType, size").execute()
        original_file_name = file_metadata.get('name')
        mime_type = file_metadata.get('mimeType')
        file_size = file_metadata.get('size')

        if not original_file_name:
            status_callback("message", f"[DriveDownloader-WARN] Không thể lấy tên file cho ID: {file_id}. Bỏ qua.")
            return False, f"Không có tên file cho ID {file_id}"

        local_file_path = os.path.join(download_dir, original_file_name)

        counter = 1
        base_name, ext = os.path.splitext(local_file_path)
        while os.path.exists(local_file_path):
            local_file_path = f"{base_name} ({counter}){ext}"
            counter += 1

        if counter > 1:
            final_file_name_on_disk = os.path.basename(local_file_path)
            status_callback("message", f"[DriveDownloader-INFO] File '{original_file_name}' đã tồn tại. Lưu thành '{final_file_name_on_disk}'.")
            original_file_name = final_file_name_on_disk

        status_callback("metadata", {
            "name": original_file_name,
            "size": file_size if file_size is not None else 0,
            "file_id": file_id,
            "mime_type": mime_type
        })

        request = None
        export_mime_type = None

        if mime_type == 'application/vnd.google-apps.document':
            export_mime_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            local_file_path = os.path.splitext(local_file_path)[0] + '.docx'
            request = drive_service.files().export_media(fileId=file_id, mimeType=export_mime_type)
            status_callback("message", f"[DriveDownloader] Exporting Google Doc '{original_file_name}' sang .docx")
        elif mime_type == 'application/vnd.google-apps.spreadsheet':
            export_mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            local_file_path = os.path.splitext(local_file_path)[0] + '.xlsx'
            request = drive_service.files().export_media(fileId=file_id, mimeType=export_mime_type)
            status_callback("message", f"[DriveDownloader] Exporting Google Sheet '{original_file_name}' sang .xlsx")
        elif mime_type == 'application/vnd.google-apps.presentation':
            export_mime_type = 'application/pdf' # Changed to PDF for broader compatibility
            local_file_path = os.path.splitext(local_file_path)[0] + '.pdf'
            request = drive_service.files().export_media(fileId=file_id, mimeType=export_mime_type)
            status_callback("message", f"[DriveDownloader] Exporting Google Slides '{original_file_name}' sang .pdf")
        elif mime_type and mime_type.startswith('application/vnd.google-apps'):
            status_callback("message", f"[DriveDownloader-WARN] Không hỗ trợ export trực tiếp cho mime type '{mime_type}' của file '{original_file_name}'. Bỏ qua.")
            return False, f"Không hỗ trợ export cho {mime_type}"
        else:
            request = drive_service.files().get_media(fileId=file_id)
            status_callback("message", f"[DriveDownloader] Tải file thông thường: '{original_file_name}'")

        if request:
            # Mở file trên đĩa cứng TRƯỚC KHI tải ở chế độ ghi nhị phân ('wb')
            with open(local_file_path, 'wb') as fh:
                # MediaIoBaseDownload sẽ ghi trực tiếp từng chunk vào file handle 'fh' này
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    try:
                        status, done = downloader.next_chunk()
                        if status:
                            status_callback("progress", {
                                "downloaded_bytes": status.resumable_progress,
                                "progress_percent": int(status.progress() * 100)
                            })
                    except HttpError as e_chunk:
                        status_callback("message", f"[DriveDownloader-ERROR] Lỗi trong khi tải chunk cho '{original_file_name}': {e_chunk}")
                        # Khi có lỗi, file chưa hoàn chỉnh sẽ được đóng.
                        return False, f"Lỗi chunk khi tải '{original_file_name}': {e_chunk}"

            # File đã được ghi hoàn chỉnh vào đĩa khi vòng lặp kết thúc.
            # Không cần ghi lại lần nữa bằng f.write(fh.getvalue()).
            final_size_on_disk = os.path.getsize(local_file_path)
            status_callback("message", f"[DriveDownloader] HOÀN TẤT tải '{original_file_name}' -> '{local_file_path}' (Kích thước: {final_size_on_disk} bytes).")
            return True, local_file_path
        else:
            # This case should ideally not be reached if original_file_name was successfully retrieved.
            # If request is None, it's likely due to an unhandled mime_type or an issue before request creation.
            status_callback("message", f"[DriveDownloader-ERROR] Không thể tạo yêu cầu tải cho file: '{original_file_name}' (ID: {file_id}). Kiểm tra mime_type: {mime_type}.")
            return False, f"Không có request nào được tạo cho file {original_file_name}"

    except HttpError as error:
        error_message_detail = f"Lỗi API Google Drive khi xử lý file ID '{file_id}': {error.resp.status} - {error._get_reason()}"
        try:
            content = json.loads(error.content.decode('utf-8'))
            if 'error' in content and 'message' in content['error']:
                error_message_detail = f"Lỗi API Google Drive (ID: {file_id}): {content['error']['message']}"
        except: # Keep the original error_message_detail if parsing fails
            pass
        # Bạn có thể thêm print(traceback.format_exc()) ở đây nếu muốn xem traceback của HttpError
        status_callback("message", f"[DriveDownloader-ERROR] {error_message_detail}")
        return False, error_message_detail # Return the detailed message
    except Exception as e:
        # ĐÂY LÀ NƠI LỖI CỦA BẠN ĐANG ĐƯỢC BẮT
        error_message_with_trace = f"Lỗi không xác định khi tải file ID '{file_id}': {type(e).__name__} - {e}"
        
        # In traceback ra console (hoặc nơi output chuẩn của bạn) để gỡ lỗi
        print(f"--- TRACEBACK LỖI TRONG download_file_from_drive (ID: {file_id}) ---")
        traceback.print_exc()
        print(f"--- KẾT THÚC TRACEBACK (ID: {file_id}) ---")
        
        # Gửi thông báo lỗi đã bao gồm tên lỗi và thông điệp lỗi gốc.
        # Traceback đầy đủ đã được in ra ở trên, hoặc sẽ được log bởi ui_script.py
        status_callback("message", f"[DriveDownloader-ERROR] {error_message_with_trace}. Xem console hoặc log ứng dụng để có traceback chi tiết.")
        return False, f"Lỗi không xác định khi tải file ID '{file_id}': {e}"