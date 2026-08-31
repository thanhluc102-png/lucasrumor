#!/usr/bin/env python3
"""Báo cáo vận hành mỗi sáng, gửi vào Telegram.

  python daily_report.py           # gửi thật
  python daily_report.py --dry     # chỉ in ra màn hình, KHÔNG gửi

Gom 24h qua của cả 3 repo rồi trả lời đúng 3 câu: đêm qua máy làm gì, kết quả ra
sao, và hôm nay cần mình xử gì. Đặt ở repo này vì TELEGRAM_TOKEN/CHAT_ID đã có sẵn
ở đây; hai repo kia đọc chéo qua raw.githubusercontent (cả 3 đều public).
"""
import os
import sys
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone

VN = timezone(timedelta(hours=7))
NOW = datetime.now(VN)
SINCE = NOW - timedelta(hours=24)

OWNER = "thanhluc102-png"
REPOS = {                       # tên hiển thị -> repo
    "Reel cutout": "lucas-cutout-reel",
    "Rumor": "lucasrumor",
    "Reel daily": "lucas-daily-reel",
}

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def get_json(url, token=None):
    req = urllib.request.Request(url, headers={"User-Agent": "lucas-daily-report"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def parse_time(s):
    """publish_time không đồng nhất giữa 2 repo: bên reel ghi UTC có hậu tố Z,
    bên rumor ghi datetime.now() trần không kèm múi giờ. Chuẩn hoá hết về giờ VN,
    cái nào không có múi giờ thì coi như đã là giờ VN."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(VN) if dt.tzinfo else dt.replace(tzinfo=VN)


def recent(rows, key="publish_time"):
    out = []
    for r in rows:
        t = parse_time(r.get(key))
        if t and t >= SINCE:
            out.append((t, r))
    return sorted(out, key=lambda x: x[0])


def score_of(r):
    return (r.get("performance") or {}).get("score")


def ci_failures(token):
    """Job đỏ trong 24h. Lỗi mạng thì báo 'không kiểm được' chứ không im lặng
    bỏ qua — báo cáo nói 'CI ổn' trong khi thật ra chưa hỏi được là tệ hơn."""
    bad, unknown = [], []
    since_iso = SINCE.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for label, repo in REPOS.items():
        url = (f"https://api.github.com/repos/{OWNER}/{repo}/actions/runs"
               f"?created=%3E{urllib.parse.quote(since_iso)}&per_page=50")
        try:
            runs = get_json(url, token).get("workflow_runs", [])
        except Exception as e:
            unknown.append(f"{label} ({type(e).__name__})")
            continue
        for run in runs:
            if run.get("conclusion") in ("failure", "timed_out", "cancelled"):
                bad.append(f"{label}: {run.get('name')} — {run.get('conclusion')}")
    return bad, unknown


def load_reels():
    url = (f"https://raw.githubusercontent.com/{OWNER}/"
           f"{REPOS['Reel cutout']}/main/reels_history.json")
    try:
        return get_json(url), None
    except Exception as e:
        return [], f"{type(e).__name__}"


def load_rumors():
    """Đọc bản trên GitHub chứ KHÔNG đọc file local, kể cả khi chạy ngay trong repo
    này. Bản checkout ở máy có thể cũ vài ngày -> báo cáo phun ra '0 bài trong 24h,
    pipeline chết' trong khi thực tế vẫn chạy đều. Cảnh báo giả kiểu đó dùng vài lần
    là mất luôn độ tin của cả báo cáo. Local chỉ dùng khi mạng hỏng."""
    url = f"https://raw.githubusercontent.com/{OWNER}/{REPOS['Rumor']}/main/post_history.json"
    try:
        return get_json(url), None
    except Exception as e:
        try:
            with open("post_history.json", encoding="utf-8") as f:
                return json.load(f), f"đọc bản local (không tải được từ GitHub: {type(e).__name__})"
        except Exception:
            return [], f"{type(e).__name__}"


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def build():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    reels_all, reels_err = load_reels()
    rumors_all, rumors_err = load_rumors()
    bad_ci, unknown_ci = ci_failures(token)

    reels = recent(reels_all)
    rumors = recent(rumors_all)

    L = [f"<b>☀️ BÁO CÁO SÁNG {NOW.strftime('%d/%m/%Y')}</b>",
         f"<i>24h tính tới {NOW.strftime('%H:%M')}</i>", ""]

    # --- 1. Đêm qua máy làm gì ---
    L.append("<b>1. Máy đã chạy</b>")
    if reels_err:
        L.append(f"• Reel: ⚠️ không đọc được lịch sử ({reels_err})")
    else:
        L.append(f"• Reel cutout: <b>{len(reels)}</b> video")
        for t, r in reels[-4:]:
            hook = (r.get("hook") or r.get("product_name") or "(không tên)")[:52]
            L.append(f"   {t.strftime('%H:%M')} — {esc(hook)}")
    if rumors_err:
        L.append(f"• Rumor: ⚠️ {rumors_err}")
    else:
        L.append(f"• Bài rumor: <b>{len(rumors)}</b> bài")
        for t, r in rumors[-4:]:
            L.append(f"   {t.strftime('%H:%M')} — {esc((r.get('title') or '')[:52])}")
    L.append("")

    # --- 2. Kết quả ---
    L.append("<b>2. Tương tác</b>")
    scored = [(t, r) for t, r in rumors + reels if score_of(r) is not None]
    if not scored:
        L.append("• Chưa có số liệu (tương tác thường về sau vài tiếng)")
    else:
        vals = sorted(score_of(r) for _, r in scored)
        med = vals[len(vals) // 2]
        best = max(scored, key=lambda x: score_of(x[1]))
        L.append(f"• Trung vị <b>{med}</b> điểm trên {len(vals)} bài đã có số")
        L.append(f"• Cao nhất: {score_of(best[1])} — {esc((best[1].get('title') or best[1].get('hook') or '')[:46])}")
    L.append("")

    # --- 3. Việc cần xử ---
    todo = []
    if bad_ci:
        todo += [f"🔴 {esc(x)}" for x in bad_ci]
    if unknown_ci:
        todo.append(f"⚠️ Không kiểm được CI của: {esc(', '.join(unknown_ci))}")
    # Pipeline chết IM LẶNG là ca tệ nhất: CI xanh nhưng không ra bài nào. Nếu chỉ
    # nhìn job đỏ thì không bao giờ phát hiện.
    if not reels_err and not reels:
        todo.append("🔴 Không có reel nào đăng trong 24h — kiểm tra pipeline")
    if not rumors_err and not rumors:
        todo.append("🔴 Không có bài rumor nào trong 24h — kiểm tra pipeline")
    zero = [r for _, r in scored if score_of(r) == 0]
    if zero:
        todo.append(f"🟡 {len(zero)} bài không ai tương tác (0 điểm)")
    noname = [r for _, r in reels if not (r.get("product_name") or "").strip()]
    if noname:
        todo.append(f"🟡 {len(noname)} reel thiếu tên sản phẩm trong lịch sử")

    L.append("<b>3. Cần bạn xử</b>")
    L += [f"• {x}" for x in todo] if todo else ["• Không có gì bất thường ✅"]

    return "\n".join(L)


def send(text):
    tok = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        print("Thiếu TELEGRAM_TOKEN / TELEGRAM_CHAT_ID — không gửi được.", file=sys.stderr)
        return False
    data = urllib.parse.urlencode({
        "chat_id": chat, "text": text, "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        ok = json.loads(r.read().decode()).get("ok")
    print("Đã gửi Telegram." if ok else "Telegram từ chối tin nhắn.")
    return bool(ok)


if __name__ == "__main__":
    msg = build()
    if "--dry" in sys.argv:
        print(msg)
    else:
        send(msg)
