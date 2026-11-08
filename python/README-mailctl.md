# mailctl：邮件转发器管理工具

`mailctl` 统一管理 `mail_forwarder_pro.py`，提供外部配置、旧 UID 状态迁移、单实例运行、用户级 systemd、网络诊断和状态备份。

它只管理保留原邮件内容的 **Resent 转发实现**，不管理会重写邮件头的 `auto_forward.py`。不要同时运行多个邮件转发脚本，否则可能重复转发或互相覆盖 UID 状态。

## 特点

- 邮箱授权码不再写入 Python 源码或命令行参数。
- UID 状态使用固定绝对路径，不受启动目录影响。
- UID 状态原子保存；文件损坏时停止运行，不会静默当成空状态重新转发。
- `flock` 防止通过 `mailctl` 重复启动多个实例。
- 用户级 systemd 负责启停、重启和日志，无需 `nohup`、PID 查找或 `pkill`。
- `doctor --network` 只认证 IMAP/SMTP，不读取邮件、不发送测试邮件、不修改 UID。
- 备份只包含 UID 状态和校验清单，不包含授权码、源码或日志。

## 环境要求

- Linux，Python 3，标准库即可，无第三方 Python 依赖。
- 后台服务命令需要支持 `systemctl --user` 和 `journalctl --user` 的环境。
- 邮箱需开启 IMAP/SMTP，并使用客户端授权码或独立应用密码。

## 快速开始

```bash
cd /opt/workspace/zml/code-fragment/python

# 1. 交互创建配置；授权码输入不回显
./mailctl init

# 2. 先检查真实 IMAP/SMTP 登录，不读取或发送邮件
./mailctl doctor --network

# 3. 安装并启用用户服务，此步骤不会自动启动
./mailctl install --user

# 4. 明确启动
./mailctl start
./mailctl status
```

初始化时会询问：

- IMAP 主机和端口，默认 `imap.mxhichina.com:993`
- SMTP 主机和端口，默认 `smtp.mxhichina.com:587`
- 源邮箱账号、转发目标邮箱和授权码
- 轮询间隔默认 5 秒，连接超时默认 15 秒

自动化环境可通过 `MAILCTL_PASSWORD` 环境变量提供授权码，并使用 `--account`、`--target`、`--imap-host`、`--smtp-host` 等参数避免交互。不要把授权码直接写进 shell 历史、脚本或 `config.json`。

## 文件位置

默认遵循 XDG 目录：

| 内容 | 默认路径 |
| --- | --- |
| 非敏感配置 | `~/.config/mailctl/config.json` |
| 授权码环境文件 | `~/.config/mailctl/secrets.env` |
| UID 状态 | `~/.local/state/mailctl/forwarded_uids.json` |
| 单实例锁 | `~/.local/state/mailctl/run.lock` |
| 状态备份 | `~/.local/state/mailctl/backups/` |
| 用户服务 | `~/.config/systemd/user/mailctl.service` |

配置、秘密和状态文件使用 `0600`，私有运行目录使用 `0700`。已有配置不会被 `init` 静默覆盖。

可为所有命令指定其他路径，全局参数必须放在子命令前：

```bash
./mailctl --config /path/to/config.json --state-dir /path/to/state doctor
```

## 旧 UID 状态迁移

`init` 默认检查同目录下的旧文件：

```text
python/forwarded_uids.json
```

如果存在，会校验后复制到新的固定状态目录，并保留旧文件。若新位置已有状态，则拒绝用旧文件覆盖。也可指定其他 JSON 状态：

```bash
./mailctl init --legacy-state /path/to/forwarded_uids.json
```

`processed_uids.txt` 来自另一种转发实现，其格式和邮箱语义不同，**不会自动合并**。迁移前应停止直接运行旧脚本的进程；`mailctl` 的实例锁只能约束通过 `mailctl` 启动的实例。

## 常用命令

```bash
# 离线检查配置、权限、UID JSON 和目录
./mailctl doctor

# 额外测试 IMAP TLS 登录、INBOX 只读选择和 SMTP STARTTLS 认证
./mailctl doctor --network

# 前台运行，主要用于 systemd 或调试
./mailctl run

# 安装/启用用户服务，但不自动启动
./mailctl install --user

# 服务管理
./mailctl start
./mailctl stop
./mailctl restart
./mailctl status

# 查看最近 50 行日志，或持续跟踪
./mailctl logs
./mailctl logs --follow
./mailctl logs --lines 200

# 备份 UID 状态
./mailctl backup
```

`status` 在服务停止时可能返回非零状态，这是 `systemctl` 的正常行为。进程处于 active 只代表进程存活，不代表最近一轮 IMAP/SMTP 操作成功，应结合日志和 `doctor --network` 判断。

默认用户服务通常依赖用户会话。如果确需未登录也持续运行，可由管理员另行配置 linger；`mailctl` 不会自动修改这项系统设置。

## 配置示例

`config.json` 只保存非敏感配置：

```json
{
  "imap_host": "imap.mxhichina.com",
  "imap_port": 993,
  "smtp_host": "smtp.mxhichina.com",
  "smtp_port": 587,
  "email_account": "source@example.com",
  "target_email": "target@example.com",
  "password_env": "MAILCTL_PASSWORD",
  "check_interval": 5,
  "connection_timeout": 15,
  "backup_keep": 10
}
```

`secrets.env` 由工具生成：

```text
MAILCTL_PASSWORD="你的客户端授权码"
```

运行时优先读取 `password_env` 指定的环境变量；环境中没有该变量时才读取 `secrets.env`。不要在 `config.json` 中增加 `password` 或 `email_password`，工具会拒绝这种配置。

## UID 备份

```bash
./mailctl backup
```

每次生成一个 `mailctl-时间戳.tar.gz`，其中只有：

- `forwarded_uids.json`
- `manifest.json`：创建时间、UID 数量和状态 SHA-256

默认保留最近 10 份，可通过 `backup_keep` 调整。归档权限为 `0600`。恢复前应先停止服务、校验清单并备份当前状态，不要在运行中直接覆盖 UID 文件。

## 故障排查

### 提示已有实例运行

```bash
./mailctl status
./mailctl logs --lines 100
```

确认旧服务或手工 `run` 已停止。不要同时直接运行 `mail_forwarder_pro.py`、`aliyun.py` 等其他实现。

### UID 状态损坏

工具会拒绝启动和备份，不会将其当成空数组。先停止服务，从可信备份恢复或人工修复 JSON；直接清空状态可能把当前未读邮件再次转发。

### 文件权限过宽

```bash
chmod 700 ~/.config/mailctl ~/.local/state/mailctl
chmod 600 ~/.config/mailctl/config.json \
  ~/.config/mailctl/secrets.env \
  ~/.local/state/mailctl/forwarded_uids.json
```

### 网络或认证失败

```bash
./mailctl doctor --network
./mailctl logs --lines 100
```

分别查看 IMAP 和 SMTP 结果。检查授权码、服务是否开启、网络/DNS 和 TLS。网络诊断不会发送邮件，因此不能替代一次受控的真实端到端转发验证。

## 安全说明

- 原脚本曾包含内联凭据；迁移到外部配置后，仍应尽快轮换旧授权码，并检查旧源码副本、备份和 Git 历史。
- 日志可能包含邮件主题和发件人，属于敏感数据，不应随普通诊断包外发。
- `mailctl` 会脱敏配置中的账号、目标和授权码，但无法保证任意邮件服务器响应中不含其他隐私信息。
- 备份不包含授权码，但 UID 状态仍应按私有数据处理。

## 离线测试

```bash
cd /opt/workspace/zml/code-fragment
python3 -m unittest discover -s python/tests -p 'test_mail*.py' -v
```

测试使用临时目录和假 IMAP/SMTP 对象，不连接真实邮箱、不安装或启动真实服务、不发送邮件。
