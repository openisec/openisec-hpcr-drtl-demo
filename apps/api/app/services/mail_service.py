import httpx
import logging

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


async def send_email(to: str, subject: str, html: str) -> bool:
    """
    Send an email via Resend API.
    Returns True on success, False on failure.
    Failures are logged but never raised, so callers can return
    a generic success response (anti email-enumeration).
    """
    if not settings.RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not configured; skipping email send")
        return False

    headers = {
        "Authorization": f"Bearer {settings.RESEND_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "from": settings.MAIL_FROM,
        "to": [to],
        "subject": subject,
        "html": html,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(RESEND_API_URL, headers=headers, json=payload)
            if response.status_code >= 400:
                logger.error(f"Resend API error {response.status_code}: {response.text}")
                return False
            return True
    except httpx.HTTPError as e:
        logger.error(f"Failed to send email via Resend: {e}")
        return False


async def send_password_reset_email(to: str, reset_url: str) -> bool:
    subject = "Openisec HPCR-DRTL - Password Reset Request"
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
      <h2 style="color: #1e3a5f;">Password Reset Request</h2>
      <p>We received a request to reset the password for your Openisec HPCR-DRTL account.</p>
      <p>
        <a href="{reset_url}"
           style="display:inline-block; background:#0ea5e9; color:#fff; padding:10px 20px; border-radius:6px; text-decoration:none;">
          Reset Password
        </a>
      </p>
      <p>This link will expire in {settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes.</p>
      <p>If you did not request this, you can safely ignore this email.</p>
    </div>
    """
    return await send_email(to, subject, html)


async def send_risk_alert_email(to: str, session_title: str, risk_score: int, session_url: str) -> bool:
    """
    G. 分析結果のリスクスコアが組織の閾値以上と判明した直後、承認者へ
    送る内容確認メール(この時点ではまだ承認は不要。ステータスは
    「進行中(open)」のまま)。
    """
    subject = f"Openisec HPCR-DRTL - リスクスコア{risk_score}のログにご注意ください"
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
      <h2 style="color: #b45309;">リスクスコアが高い意思決定ログがあります</h2>
      <p>「{session_title}」のリスクスコアが <strong>{risk_score}/100</strong> と判定されました。</p>
      <p>この時点ではまだ承認は不要です。利用者が決定を記録(Log)した際に、改めて承認依頼メールをお送りします。</p>
      <p>
        <a href="{session_url}"
           style="display:inline-block; background:#0ea5e9; color:#fff; padding:10px 20px; border-radius:6px; text-decoration:none;">
          内容を確認する
        </a>
      </p>
    </div>
    """
    return await send_email(to, subject, html)


async def send_approval_request_email(to: str, session_title: str, risk_score: int, session_url: str) -> bool:
    """
    G. 利用者がLog(決定記録)を実施し、リスクスコアが組織の閾値以上のため
    承認が必要になった際に、承認者へ送る承認依頼メール。承認者のうち
    誰か一人が承認すれば完了となる。
    """
    subject = f"Openisec HPCR-DRTL - 承認をお願いします(リスクスコア{risk_score})"
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
      <h2 style="color: #b45309;">承認が必要な意思決定ログがあります</h2>
      <p>「{session_title}」(リスクスコア {risk_score}/100)の決定内容について、承認をお願いします。</p>
      <p>承認者のどなたか一人が承認すれば完了となります。</p>
      <p>
        <a href="{session_url}"
           style="display:inline-block; background:#0ea5e9; color:#fff; padding:10px 20px; border-radius:6px; text-decoration:none;">
          承認する / 差し戻す
        </a>
      </p>
    </div>
    """
    return await send_email(to, subject, html)


async def send_rejection_email(
    to: str, session_title: str, approver_name: str, comment: str | None, session_url: str
) -> bool:
    """
    G. 承認者が差し戻した際、作成者(利用者)へ送る通知メール。
    セッションは「進行中(open)」に戻っており、Decision/Reason/Targetを
    修正のうえ再度Logする必要があることを伝える。
    """
    subject = "Openisec HPCR-DRTL - 決定内容が差し戻されました"
    comment_html = (
        f'<p style="background:#1e293b; padding:12px 16px; border-radius:6px; color:#e2e8f0;">{comment}</p>'
        if comment
        else ""
    )
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
      <h2 style="color: #ea580c;">決定内容が差し戻されました</h2>
      <p>「{session_title}」について、承認者({approver_name})より差し戻されました。</p>
      {comment_html}
      <p>Decision・Reason・実施ターゲット日を必要に応じて修正のうえ、再度Logしてください。</p>
      <p>
        <a href="{session_url}"
           style="display:inline-block; background:#0ea5e9; color:#fff; padding:10px 20px; border-radius:6px; text-decoration:none;">
          内容を確認して修正する
        </a>
      </p>
    </div>
    """
    return await send_email(to, subject, html)

async def send_verification_email(to: str, verify_url: str) -> bool:
    subject = "Openisec HPCR-DRTL - \u30e1\u30fc\u30eb\u30a2\u30c9\u30ec\u30b9\u306e\u3054\u78ba\u8a8d"
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
      <h2 style="color: #1e3a5f;">\u30a2\u30ab\u30a6\u30f3\u30c8\u4f5c\u6210 - \u30e1\u30fc\u30eb\u30a2\u30c9\u30ec\u30b9\u306e\u78ba\u8a8d</h2>
      <p>Openisec HPCR-DRTL\u306e\u30a2\u30ab\u30a6\u30f3\u30c8\u4f5c\u6210\u3092\u958b\u59cb\u3044\u305f\u3060\u304d\u3001\u3042\u308a\u304c\u3068\u3046\u3054\u3056\u3044\u307e\u3059\u3002</p>
      <p>\u4ee5\u4e0b\u306e\u30dc\u30bf\u30f3\u304b\u3089\u3001\u672c\u767b\u9332\u3078\u304a\u9032\u307f\u304f\u3060\u3055\u3044\u3002</p>
      <p>
        <a href="{verify_url}"
           style="display:inline-block; background:#0ea5e9; color:#fff; padding:10px 20px; border-radius:6px; text-decoration:none;">
          \u672c\u767b\u9332\u3078\u9032\u3080
        </a>
      </p>
      <p>\u3053\u306e\u30ea\u30f3\u30af\u306e\u6709\u52b9\u671f\u9650\u306f{settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES}\u5206\u3067\u3059\u3002</p>
      <p>\u5fc3\u5f53\u305f\u308a\u304c\u306a\u3044\u5834\u5408\u306f\u3001\u3053\u306e\u30e1\u30fc\u30eb\u3092\u7834\u68c4\u3057\u3066\u304f\u3060\u3055\u3044\u3002</p>
    </div>
    """
    return await send_email(to, subject, html)

