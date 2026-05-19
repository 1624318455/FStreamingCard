# FStreamingCard Gateway Patches

这些补丁是 FStreamingCard 对 Hermes Gateway `feishu.py` 的修改，使 `/help` 命令输出交互式卡片而非纯文字。

## 补丁列表

### feishu_py_help_card.patch

对 `~/.hermes/hermes-agent/gateway/platforms/feishu.py` 的 3 处修改：

1. **第 2121 行** — ▶ 按钮 cmd 正则修复
   - `cmd_name.split()[0]` → `re.sub(r'\s*[\[<][^\]>]*[\]>]', '', cmd_name).strip()`
   - 修复多词命令（如 `hermes config`）被截断的问题

2. **`_dispatch_inbound_event`** — /help 拦截
   - 检测到 `/help` 命令后调 sidecar `/help` 发交互卡片
   - 成功则跳过 gateway 默认文字响应，失败降级

3. **`_forward_help_to_sidecar`** — 新增方法
   - 调用 sidecar `POST /help` 发送交互卡片到群聊
   - 使用 aiohttp，3 秒超时，静默降级

## 应用方式

```bash
# 手动修改 feishu.py（参考 patches/feishu_py_help_card.patch）
# 然后重启网关
hermes gateway restart
```

## 注意

- 这些补丁直接修改 Hermes 网关文件，不在 FStreamingCard 仓库的 git 管理中
- 升级 Hermes 后需要重新应用补丁
- 补丁基于 Hermes v0.14.x，其他版本可能需要调整行号
