
import imaplib
import smtplib
import ssl
import time
import json
import logging
import email
import os
import tempfile
from email.utils import formatdate, parseaddr
from email.header import decode_header

# ==========================
# 配置区域（推荐通过 mailctl 注入外部配置）
# ==========================

IMAP_HOST = "imap.mxhichina.com"
IMAP_PORT = 993
SMTP_HOST = "smtp.mxhichina.com"
SMTP_PORT = 587

EMAIL_ACCOUNT = ""
EMAIL_PASSWORD = ""
TARGET_EMAIL = ""
CHECK_INTERVAL = 5
CONNECTION_TIMEOUT = 15
UID_STORE_FILE = "forwarded_uids.json"
REQUIRE_UID_STORE = False
STOP_EVENT = None

# ==========================
# 日志
# ==========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ==========================
# UID 持久化
# ==========================

def load_forwarded_uids():
    try:
        with open(UID_STORE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        if REQUIRE_UID_STORE:
            raise
        return set()

    if not isinstance(data, list) or not all(isinstance(uid, str) for uid in data):
        raise ValueError(f"UID 状态文件格式错误: {UID_STORE_FILE}")
    return set(data)

def save_forwarded_uids(uids):
    state_path = os.path.abspath(UID_STORE_FILE)
    state_dir = os.path.dirname(state_path)
    os.makedirs(state_dir, mode=0o700, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".forwarded_uids.", suffix=".tmp", dir=state_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            os.chmod(temp_path, 0o600)
            json.dump(sorted(uids), f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, state_path)
        dir_fd = os.open(state_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)

# ==========================
# IMAP 操作
# ==========================

def connect_imap(first_connect=False):
    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, timeout=CONNECTION_TIMEOUT)

    if first_connect:
        logging.info(f"✅ 成功连接到 IMAP 服务器: {IMAP_HOST}:{IMAP_PORT}")

    mail.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)

    if first_connect:
        logging.info("✅ IMAP 登录成功")

    mail.select("INBOX", readonly=True)
    return mail

def fetch_unseen_uids(mail):
    status, response = mail.uid("search", None, "UNSEEN")
    if status != "OK":
        return []
    return response[0].split()

def fetch_raw_email(mail, uid):
    status, data = mail.uid("fetch", uid, "(BODY.PEEK[])")
    if status != "OK":
        return None
    return data[0][1]

# ==========================
# 邮件解析
# ==========================

def decode_mime_words(text):
    decoded = ""
    for part, encoding in decode_header(text):
        if isinstance(part, bytes):
            decoded += part.decode(encoding or "utf-8", errors="ignore")
        else:
            decoded += part
    return decoded

def parse_email_info(raw_email_bytes):
    msg = email.message_from_bytes(raw_email_bytes)

    subject = decode_mime_words(msg.get("Subject", ""))

    name, addr = parseaddr(msg.get("From", ""))

    if name:
        name = decode_mime_words(name)
        from_display = f"{name} <{addr}>"
    else:
        from_display = addr

    return subject, from_display

def count_attachments(raw_email_bytes):
    msg = email.message_from_bytes(raw_email_bytes)
    count = 0
    for part in msg.walk():
        if part.get_content_disposition() == "attachment":
            count += 1
    return count

# ==========================
# Resent 转发
# ==========================

def build_resent_message(raw_email_bytes):
    split_index = raw_email_bytes.find(b"\r\n\r\n")
    if split_index == -1:
        return None

    original_headers = raw_email_bytes[:split_index]
    original_body = raw_email_bytes[split_index:]

    resent_headers = (
        f"Resent-From: {EMAIL_ACCOUNT}\r\n"
        f"Resent-To: {TARGET_EMAIL}\r\n"
        f"Resent-Date: {formatdate(localtime=True)}\r\n"
        f"Sender: {EMAIL_ACCOUNT}\r\n"
    ).encode("utf-8")

    return resent_headers + original_headers + original_body

def send_raw_email(raw_message):
    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=CONNECTION_TIMEOUT) as server:
            server.starttls(context=context)
            server.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ACCOUNT, TARGET_EMAIL, raw_message)

        logging.info("📤 邮件发送成功")
        return True
    except Exception as e:
        logging.error(f"❌ 邮件发送失败: {e}")
        return False

# ==========================
# 主程序
# ==========================

def stop_requested():
    return STOP_EVENT is not None and STOP_EVENT.is_set()


def wait_for_next_check():
    if STOP_EVENT is None:
        time.sleep(CHECK_INTERVAL)
    else:
        STOP_EVENT.wait(CHECK_INTERVAL)


def main():
    logging.info("🚀 阿里云企业邮箱邮件转发器已启动")

    if not all([IMAP_HOST, SMTP_HOST, EMAIL_ACCOUNT, EMAIL_PASSWORD, TARGET_EMAIL]):
        logging.error("❌ 配置项缺失")
        return

    logging.info("✅ 所有配置项验证通过")
    logging.info(f"⏱️   定时检测间隔: {CHECK_INTERVAL} 秒")
    logging.info(f"📬 源邮箱: {EMAIL_ACCOUNT}")
    logging.info(f"📤 目标邮箱: {TARGET_EMAIL}")
    logging.info("🔁 循环执行中...按 Ctrl+C 停止")

    forwarded_uids = load_forwarded_uids()
    first_connect = True

    try:
        while not stop_requested():
            try:
                mail = connect_imap(first_connect)
                first_connect = False

                all_uids = fetch_unseen_uids(mail)

                # 只过滤需要转发的
                pending_uids = [
                    uid for uid in all_uids
                    if uid.decode() not in forwarded_uids
                ]

                if pending_uids:
                    logging.info(f"📬 本轮检测到 {len(pending_uids)} 封新邮件需要转发")
                else:
                    mail.logout()
                    wait_for_next_check()
                    continue

                for index, uid in enumerate(pending_uids, start=1):
                    if stop_requested():
                        break
                    uid_str = uid.decode()

                    raw_email = fetch_raw_email(mail, uid)
                    if not raw_email:
                        continue

                    subject, from_display = parse_email_info(raw_email)

                    logging.info(
                        f"📄 正在处理第 {index}/{len(pending_uids)} 封邮件: "
                        f"'{subject}' 来自 {from_display}"
                    )

                    attachment_count = count_attachments(raw_email)
                    logging.info(f"📎 提取到 {attachment_count} 个附件")

                    resent_message = build_resent_message(raw_email)
                    if not resent_message:
                        logging.error("❌ 邮件解析失败")
                        continue

                    if stop_requested():
                        break

                    if send_raw_email(resent_message):
                        forwarded_uids.add(uid_str)
                        save_forwarded_uids(forwarded_uids)
                        logging.info("✅ 转发完成")
                    else:
                        logging.error("📤 转发失败，跳过下一封")

                mail.logout()
                logging.info("🔒 IMAP 连接已安全关闭")

            except Exception as e:
                logging.error(f"❌ 本轮异常: {e}")

            if not stop_requested():
                logging.info(f"⏸️   等待 {CHECK_INTERVAL} 秒后进行下一次检测...")
            wait_for_next_check()

    except KeyboardInterrupt:
        logging.info("👋 用户中断，程序正常退出")

    if stop_requested():
        logging.info("👋 收到停止信号，程序正常退出")

if __name__ == "__main__":
    main()
