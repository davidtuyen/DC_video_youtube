# Superpowers Skills — Antigravity Routing Guide

Tất cả skills từ [obra/superpowers](https://github.com/obra/superpowers) đã được cài tại:
`C:\Users\PC\.antigravity-global\skills\sp-<name>\SKILL.md`

## Khi nào đọc skill nào

| Trigger / Tình huống | Skill cần đọc |
|----------------------|---------------|
| Bắt đầu build feature mới, user nói "hãy xây X" | `sp-brainstorming` → `sp-writing-plans` |
| Implement feature / bug fix | `sp-test-driven-development` |
| Có bug, test fail, hành vi lạ | `sp-systematic-debugging` |
| Sau khi fix xong, trước khi báo Done | `sp-verification-before-completion` |
| Cần chia task cho nhiều subagent song song | `sp-dispatching-parallel-agents` |
| Đang execute implementation plan | `sp-executing-plans` |
| Subagent-driven development loop | `sp-subagent-driven-development` |
| Viết plan chi tiết cho tasks | `sp-writing-plans` |
| Yêu cầu code review | `sp-requesting-code-review` |
| Nhận và xử lý code review | `sp-receiving-code-review` |
| Làm việc với git worktrees | `sp-using-git-worktrees` |
| Hoàn thành branch, merge/PR | `sp-finishing-a-development-branch` |
| Tạo skill mới | `sp-writing-skills` |

## Skill Stacking với existing Antigravity skills

```
Level 1 - Architecture:    python-pyside6-tdd / anthropic-frontend-design
Level 2 - Process:         sp-brainstorming → sp-writing-plans → sp-executing-plans
Level 3 - Quality:         sp-test-driven-development + sp-systematic-debugging
Level 4 - Code style:      python-modern-typing / claude-code-behavior
Level 5 - Review:          sp-requesting-code-review → sp-verification-before-completion
```

## Priority Rules (từ sp-using-superpowers)

1. **User instructions** (user rules, activeContext.md) — cao nhất
2. **Superpowers skills** — override default behavior
3. **Default behavior** — thấp nhất

## Cách đọc skill trong Antigravity

```python
# Ví dụ: khi gặp bug
view_file("C:\\Users\\PC\\.antigravity-global\\skills\\sp-systematic-debugging\\SKILL.md")
# → Follow the 4-phase debugging process
```
