# Prompt: Fix Git Repo Broken (Antigravity không hoạt động)

## Dùng khi nào
Khi mở thư mục trong Antigravity/VSCode mà agent không nhận project, git báo lỗi,
hoặc workspace validation fail.

## Prompt (copy & paste nguyên xi)

```
Git repo tại [ĐƯỜNG DẪN] đang bị hỏng, Antigravity không hoạt động.
Hãy kiểm tra và fix theo thứ tự sau, KHÔNG đoán mò:

1. Đọc Antigravity log tại:
   C:\Users\PC\AppData\Roaming\Antigravity\logs\<session mới nhất>\window*\exthost\vscode.git\Git.log

2. Kiểm tra git internals tại [ĐƯỜNG DẪN]:
   - .git/config  (xem extensions, worktreeConfig)
   - git worktree list --porcelain
   - git status --short
   - ls-files --others --exclude-standard | head -30
   - Kiểm tra .gitignore có tồn tại không

3. Tìm và fix:
   - File bị track ở mode 160000 (submodule ghost) nhưng không tồn tại trên disk
   - .claude/worktrees/* bị track trong index
   - Binary/cache/config bị dirty không cần thiết
   - extensions.worktreeConfig = true không cần thiết

4. Sau khi fix: git status --short phải chỉ còn file source code thực sự.
```

## Thay thế
- `[ĐƯỜNG DẪN]` → path thực tế, ví dụ: `C:\Users\PC\Desktop\CODE\MyProject`

## Nguyên nhân phổ biến (từ kinh nghiệm thực tế)
| Triệu chứng | Nguyên nhân |
|-------------|-------------|
| `fatal: not a git repository` trong log nhưng .git/ có tồn tại | `.claude/worktrees/` bị track như submodule (mode 160000) mà đã xóa |
| git status rất chậm / timeout | Không có .gitignore, binary/node_modules bị track |
| Antigravity không nhận workspace | Git index dirty/corrupt → agent fail silent |
| `worktreeConfig = true` trong .git/config | Claude Code tạo worktree rồi bị xóa không sạch |
