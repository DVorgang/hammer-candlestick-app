import logging
import html
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def _format_ai_list(items):
    if not items:
        return "<li>No major items were returned by the AI analyst.</li>"
    return "".join(f"<li>{html.escape(str(item))}</li>" for item in items)


def _format_ai_analysis_section(ai_analysis):
    if not ai_analysis:
        return ""

    status = html.escape(str(ai_analysis.get("status", "Available")))
    summary = html.escape(str(ai_analysis.get("summary", "")))
    takeaway = html.escape(str(ai_analysis.get("plain_english_takeaway", "")))
    caution_flags = _format_ai_list(ai_analysis.get("caution_flags") or [])
    supporting_context = _format_ai_list(ai_analysis.get("supporting_context") or [])
    ai_model = html.escape(str(ai_analysis.get("ai_model_used", "Groq AI")))

    return f"""
    <!-- AI Analyst Notes -->
    <div style="background-color: #fffaf0; border-left: 4px solid #ed8936; padding: 16px; border-radius: 0 8px 8px 0; margin-bottom: 24px;">
        <h3 style="margin-top: 0; margin-bottom: 8px; font-size: 15px; font-weight: 700; color: #1a202c;">AI Analyst Notes ({ai_model})</h3>
        <span style="display: inline-block; background-color: #feebc8; color: #7b341e; font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 9999px; margin-bottom: 10px;">{status}</span>
        <span style="display: inline-block; background-color: #edf2f7; color: #4a5568; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 9999px; margin-bottom: 10px; margin-left: 6px;">🤖 {ai_model}</span>
        <p style="margin: 0 0 12px 0; font-size: 13px; line-height: 1.5; color: #2d3748;">{summary}</p>
        <p style="margin: 0 0 6px 0; font-size: 13px; font-weight: 700; color: #2d3748;">Caution flags to know:</p>
        <ul style="margin: 0 0 12px 0; padding-left: 20px; font-size: 13px; color: #4a5568; line-height: 1.5;">{caution_flags}</ul>
        <p style="margin: 0 0 6px 0; font-size: 13px; font-weight: 700; color: #2d3748;">Helpful context:</p>
        <ul style="margin: 0 0 12px 0; padding-left: 20px; font-size: 13px; color: #4a5568; line-height: 1.5;">{supporting_context}</ul>
        <p style="margin: 0; font-size: 13px; line-height: 1.5; color: #2d3748;"><strong>Plain-English AI takeaway:</strong> {takeaway}</p>
    </div>
    """


def get_alert_category_and_emoji(pattern_type, score):
    """
    Translates technical pattern and score into the alert hierarchy:
    - Hammer + High/Medium Score -> "🟢 Buy Opportunity Alert"
    - Hanging Man + Medium Score -> "🟡 Risk Alert"
    - Hanging Man + High Score -> "🔴 Sell Alert"
    """
    if pattern_type == "Hammer":
        return "🟢 Buy Opportunity Alert", "High Opportunity" if score >= 70 else "Medium Opportunity"
    elif pattern_type == "Hanging Man":
        if score >= 70:
            return "🔴 Sell Alert", "High Risk Reversal"
        else:
            return "🟡 Risk Alert", "Potential Trend Weakness"
    return "⚪ Market Alert", "Neutral"

def format_alert_email(signal, token, base_url="http://localhost:8501"):
    """
    Formats a beginner-friendly HTML / Markdown email alert using the
    technical data items mapped to clean copywriting.
    """
    ticker = signal["ticker"]
    pattern_type = signal["pattern_type"]
    score = signal["confidence_score"]
    rsi = signal["rsi_14"]
    vol_mult = signal["vol_mult"]
    
    day1_date = signal["day1_date"]
    if hasattr(day1_date, "strftime"):
        day1_date_str = day1_date.strftime("%Y-%m-%d")
    else:
        day1_date_str = str(day1_date)[:10]
        
    day1_close = signal["day1_close"]
    day1_low = signal["day1_low"]
    day1_high = signal["day1_high"]
    
    alert_title, intensity = get_alert_category_and_emoji(pattern_type, score)
    
    entry_est = signal.get("day3_open") or signal.get("day2_close")
    
    epsilon = 0.01
    if pattern_type == "Hammer":
        stop_loss = day1_low - epsilon
        risk = entry_est - stop_loss
        profit_target = entry_est + (2.0 * risk) if risk > 0 else entry_est * 1.05
        blueprint_intro = (
            f"This section turns the signal into a simple plan: where the trade idea starts, where it is probably "
            f"wrong, and where the first profit target would be. For this alert, the app is watching ${entry_est:.2f} "
            f"as the possible buy area. If {ticker} falls to about ${stop_loss:.2f}, the setup is likely failing. "
            f"If {ticker} rises toward ${profit_target:.2f}, the setup is working. The plan risks about "
            f"${risk:.2f} per share to aim for about ${abs(profit_target - entry_est):.2f} per share, which is a "
            "2-to-1 reward/risk setup."
        )
        entry_label = "Possible Buy Price"
        entry_help = (
            f"If you choose to act on this alert, ${entry_est:.2f} is the price area the app is using as the "
            "starting point for the plan. Buying far above this price can make the trade riskier."
        )
        stop_help = (
            f"If {ticker} falls to about ${stop_loss:.2f}, the bullish reversal idea is likely not working. "
            "This is the suggested exit area to help limit losses."
        )
        target_help = (
            f"${profit_target:.2f} is the first profit-taking goal. It is calculated so the possible gain is about "
            "two times larger than the possible loss."
        )
        next_step_help = (
            "Beginner version: watch whether price can stay above the buy area. If it breaks below the stop area, "
            "the setup has failed. If it climbs toward the target, the trade is working."
        )
    else:
        stop_loss = day1_high + epsilon
        risk = stop_loss - entry_est
        profit_target = entry_est - (2.0 * risk) if risk > 0 else entry_est * 0.95
        blueprint_intro = (
            f"This section turns the warning signal into a simple risk plan: where to review the position, where the "
            f"warning is probably wrong, and where the downside target would be. For this alert, the app is watching "
            f"${entry_est:.2f} as the review area. If {ticker} rises to about ${stop_loss:.2f}, the warning is likely "
            f"failing. If {ticker} falls toward ${profit_target:.2f}, the warning is playing out. The plan risks about "
            f"${risk:.2f} per share to watch for about ${abs(profit_target - entry_est):.2f} per share of downside move."
        )
        entry_label = "Risk Review Price"
        entry_help = (
            f"${entry_est:.2f} is the price area the app is using to judge the warning. If you own {ticker}, this is "
            "where you may want to review whether to hold, reduce, or protect the position."
        )
        stop_help = (
            f"If {ticker} rises to about ${stop_loss:.2f}, the bearish warning is likely not working. "
            "A move above this area suggests buyers are still in control."
        )
        target_help = (
            f"${profit_target:.2f} is the downside watch area. It is calculated so the possible move is about "
            "two times larger than the risk area."
        )
        next_step_help = (
            "Beginner version: watch whether price weakens from the review area. If it pushes above the stop area, "
            "the warning has failed. If it drops toward the target, the warning is playing out."
        )

    risk_amount = abs(entry_est - stop_loss)
    reward_amount = abs(profit_target - entry_est)
        
    if pattern_type == "Hammer":
        explanation = (
            f"<strong>{ticker}</strong> may be showing a potential <strong>buying opportunity</strong>. "
            f"The stock formed a 'Hammer' candle shape on {day1_date_str}, which means that although sellers "
            f"pushed the price down during the day, buyers stepped in aggressively to close the stock near its highs. "
            f"This suggests selling pressure is exhausted and a new upward trend might be starting."
        )
    else:
        explanation = (
            f"<strong>{ticker}</strong> may be showing a potential <strong>sell or risk-reduction signal</strong>. "
            f"The stock formed a 'Hanging Man' candle shape on {day1_date_str} after an uptrend. "
            f"This indicates that while buyers managed to push the price back up before the close, "
            f"significant sell-off pressures occurred during the day. This represents potential trend weakness "
            f"and a warning that the price might reverse downwards."
        )

    manage_url = f"{base_url}/?token={token}"
    unsubscribe_url = f"{base_url}/?token={token}&unsubscribe=true"
    ai_analysis_section = _format_ai_analysis_section(signal.get("ai_analysis"))
    
    html_content = f"""
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff; color: #1a202c;">
    
    <!-- Header -->
    <div style="border-bottom: 2px solid #edf2f7; padding-bottom: 16px; margin-bottom: 20px;">
        <span style="font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #718096; display: block; margin-bottom: 4px;">Candlestick Sentinel Alert</span>
        <h1 style="font-size: 22px; font-weight: 800; margin: 0; color: #1a202c;">{alert_title}</h1>
        <span style="display: inline-block; background-color: #edf2f7; color: #4a5568; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 9999px; margin-top: 6px;">{intensity}</span>
    </div>
    
    <!-- Copy / Explanation -->
    <div style="font-size: 15px; line-height: 1.6; color: #2d3748; margin-bottom: 24px;">
        <p>{explanation}</p>
    </div>
    
    <!-- Action Plan Box -->
    <div style="background-color: #f7fafc; border-left: 4px solid { '#38a169' if pattern_type == 'Hammer' else '#e53e3e' }; padding: 16px; border-radius: 0 8px 8px 0; margin-bottom: 24px;">
        <h3 style="margin-top: 0; margin-bottom: 8px; font-size: 15px; font-weight: 700; color: #1a202c;">Trading Blueprint</h3>
        <p style="margin: 0 0 12px 0; font-size: 13px; line-height: 1.5; color: #4a5568;">{blueprint_intro}</p>
        <table style="width: 100%; font-size: 14px; border-collapse: collapse;">
            <tr>
                <td style="padding: 4px 0; color: #718096;">{entry_label}</td>
                <td style="padding: 4px 0; font-weight: 700; text-align: right;">${entry_est:.2f}</td>
            </tr>
            <tr>
                <td style="padding: 4px 0; color: #718096;">Stop-Loss / Exit If Wrong</td>
                <td style="padding: 4px 0; font-weight: 700; text-align: right; color: #e53e3e;">${stop_loss:.2f}</td>
            </tr>
            <tr>
                <td style="padding: 4px 0; color: #718096;">First Profit Target</td>
                <td style="padding: 4px 0; font-weight: 700; text-align: right; color: #38a169;">${profit_target:.2f}</td>
            </tr>
        </table>
        <div style="margin-top: 14px; padding-top: 12px; border-top: 1px solid #e2e8f0;">
            <p style="margin: 0 0 8px 0; font-size: 13px; line-height: 1.5; color: #2d3748;"><strong>1. What the entry means:</strong> {entry_help}</p>
            <p style="margin: 0 0 8px 0; font-size: 13px; line-height: 1.5; color: #2d3748;"><strong>2. What the stop means:</strong> {stop_help}</p>
            <p style="margin: 0 0 8px 0; font-size: 13px; line-height: 1.5; color: #2d3748;"><strong>3. What the target means:</strong> {target_help}</p>
            <p style="margin: 0 0 8px 0; font-size: 13px; line-height: 1.5; color: #2d3748;"><strong>Risk math:</strong> This plan risks about ${risk_amount:.2f} per share to aim for about ${reward_amount:.2f} per share.</p>
            <p style="margin: 0; font-size: 13px; line-height: 1.5; color: #2d3748;"><strong>Plain-English takeaway:</strong> {next_step_help}</p>
        </div>
    </div>

    {ai_analysis_section}
    
    <!-- Technical Details Accordion-like Footer -->
    <div style="border-top: 1px solid #edf2f7; padding-top: 16px; margin-bottom: 24px;">
        <h4 style="margin-top: 0; margin-bottom: 10px; font-size: 13px; font-weight: 700; text-transform: uppercase; color: #718096; letter-spacing: 0.05em;">Technical Details (For Experienced Traders)</h4>
        <ul style="margin: 0; padding-left: 20px; font-size: 13px; color: #4a5568; line-height: 1.5;">
            <li><strong>Pattern Identified:</strong> {pattern_type} Candle Reversal</li>
            <li><strong>Sentinel Confidence Score:</strong> {score:.1f} / 100</li>
            <li><strong>Wilder's RSI (14-period):</strong> {rsi:.1f} ({ 'Oversold / Buy Support' if rsi < 40 else 'Overbought / Extension' if rsi > 60 else 'Neutral' })</li>
            <li><strong>Volume Multiplier:</strong> {vol_mult:.2f}x (relative to 20-day Volume MA)</li>
            <li><strong>Confirmation Close:</strong> ${signal.get('day2_close', 0.0):.2f} (confirmed on {signal.get('day2_date')})</li>
        </ul>
    </div>
    
    <!-- Unsubscribe / Management Footer -->
    <div style="border-top: 1px solid #edf2f7; padding-top: 16px; text-align: center; font-size: 12px; color: #a0aec0;">
        <p style="margin-bottom: 8px;">You are receiving this automated market alert because you subscribed to tracking for <strong>{ticker}</strong>.</p>
        <p style="margin: 0;">
            <a href="{manage_url}" style="color: #3182ce; text-decoration: underline; font-weight: 600;">Manage Watchlist</a> 
            &nbsp;|&nbsp; 
            <a href="{unsubscribe_url}" style="color: #e53e3e; text-decoration: underline; font-weight: 600;">Unsubscribe Completely</a>
    </div>
</div>
"""
    return html_content

def format_growth_catalyst_email(growth_res, token, base_url="http://localhost:8501"):
    """
    Formats a responsive HTML email alert for high-growth news & volume catalyst setups.
    Includes clickable news article links so readers can validate the catalyst.
    """
    ticker = html.escape(str(growth_res.get("ticker", "TICKER")))
    score = float(growth_res.get("growth_score") or 8.0)
    cat_type = html.escape(str(growth_res.get("catalyst_type", "Growth Catalyst")))
    summary = html.escape(str(growth_res.get("headline_summary", "")))
    takeaway = html.escape(str(growth_res.get("plain_english_takeaway", "")))
    vol_mult = float(growth_res.get("vol_mult") or 1.0)
    ai_model = html.escape(str(growth_res.get("ai_model_used", "Groq AI")))
    
    key_cats = "".join(f"<li>{html.escape(str(item))}</li>" for item in (growth_res.get("key_catalysts") or []))
    risks = "".join(f"<li>{html.escape(str(item))}</li>" for item in (growth_res.get("risks") or []))

    # Build clickable news article links section
    news_articles = growth_res.get("news_articles") or []
    news_section_html = ""
    if news_articles:
        article_rows = ""
        for idx, article in enumerate(news_articles[:5]):
            title = html.escape(str(article.get("title", "Untitled Article")))
            link = str(article.get("link", ""))
            pub_date = str(article.get("pubDate", ""))
            # Format date nicely if available
            date_display = ""
            if pub_date:
                try:
                    from email.utils import parsedate_to_datetime
                    dt = parsedate_to_datetime(pub_date)
                    date_display = dt.strftime("%b %d, %Y")
                except Exception:
                    date_display = pub_date[:16] if len(pub_date) > 16 else pub_date
            
            article_rows += f"""
            <tr>
                <td style="padding: 10px 12px; border-bottom: 1px solid #e2e8f0; vertical-align: top;">
                    <a href="{link}" style="color: #1e40af; font-size: 13px; font-weight: 600; text-decoration: none; line-height: 1.4;" target="_blank">{title} →</a>
                    <div style="font-size: 11px; color: #94a3b8; margin-top: 3px;">{date_display}</div>
                </td>
            </tr>
            """
        
        news_section_html = f"""
    <!-- News Articles Section -->
    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 0; margin-bottom: 24px; overflow: hidden;">
        <div style="background: linear-gradient(135deg, #1e3a5f 0%, #1e40af 100%); padding: 14px 20px;">
            <h3 style="margin: 0; font-size: 15px; font-weight: 700; color: #ffffff;">📰 In the News — Read the Catalysts</h3>
            <p style="margin: 4px 0 0 0; font-size: 12px; color: #93c5fd;">Click any headline below to read the full story and validate this signal</p>
        </div>
        <table style="width: 100%; border-collapse: collapse;">
            {article_rows}
        </table>
    </div>
    """

    latest_price = growth_res.get("latest_price")
    price_badge_str = f"Stock Price: <strong style='color: #ffffff;'>${float(latest_price):.2f}</strong> | " if latest_price else ""

    manage_url = f"{base_url}/?token={token}"
    unsubscribe_url = f"{base_url}/?token={token}&unsubscribe=true"

    return f"""
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);">
    
    <!-- Top Header & Banner -->
    <div style="background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%); padding: 24px; border-radius: 8px; text-align: center; margin-bottom: 24px; color: #ffffff;">
        <span style="display: inline-block; background-color: #818cf8; color: #0f172a; font-size: 11px; font-weight: 800; text-transform: uppercase; padding: 4px 12px; border-radius: 9999px; letter-spacing: 0.05em; margin-bottom: 8px;">
            🚀 Growth Catalyst Alert
        </span>
        <h1 style="margin: 0; font-size: 26px; font-weight: 800; color: #ffffff; letter-spacing: -0.02em;">{ticker} — {cat_type}</h1>
        <p style="margin: 6px 0 0 0; font-size: 14px; color: #c7d2fe;">{price_badge_str}Volume Surge: {vol_mult:.2f}x 20-Day Average | AI Engine: {ai_model} | Score: {score:.1f} / 10</p>
    </div>

    
    <!-- Growth Summary Card -->
    <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 20px; margin-bottom: 24px;">
        <h3 style="margin-top: 0; margin-bottom: 8px; font-size: 16px; font-weight: 700; color: #166534;">{ai_model} Fundamental Catalyst Overview</h3>
        <p style="margin: 0 0 12px 0; font-size: 14px; line-height: 1.5; color: #14532d; font-weight: 600;">{summary}</p>
        
        <p style="margin: 0 0 6px 0; font-size: 13px; font-weight: 700; color: #166534;">Key Growth Drivers:</p>
        <ul style="margin: 0 0 12px 0; padding-left: 20px; font-size: 13px; color: #15803d; line-height: 1.5;">{key_cats}</ul>
        
        <p style="margin: 0 0 6px 0; font-size: 13px; font-weight: 700; color: #991b1b;">Risks & Considerations:</p>
        <ul style="margin: 0 0 12px 0; padding-left: 20px; font-size: 13px; color: #b91c1c; line-height: 1.5;">{risks}</ul>
        
        <p style="margin: 0; font-size: 13px; line-height: 1.5; color: #166534;"><strong>Plain-English Takeaway:</strong> {takeaway}</p>
    </div>

        
        <p style="margin: 0 0 6px 0; font-size: 13px; font-weight: 700; color: #166534;">Key Growth Drivers:</p>
        <ul style="margin: 0 0 12px 0; padding-left: 20px; font-size: 13px; color: #15803d; line-height: 1.5;">{key_cats}</ul>
        
        <p style="margin: 0 0 6px 0; font-size: 13px; font-weight: 700; color: #991b1b;">Risks & Considerations:</p>
        <ul style="margin: 0 0 12px 0; padding-left: 20px; font-size: 13px; color: #b91c1c; line-height: 1.5;">{risks}</ul>
        
        <p style="margin: 0; font-size: 13px; line-height: 1.5; color: #166534;"><strong>Plain-English Takeaway:</strong> {takeaway}</p>
    </div>
    
    {news_section_html}
    
    <!-- Footer -->
    <div style="border-top: 1px solid #edf2f7; padding-top: 16px; text-align: center; font-size: 12px; color: #a0aec0;">
        <p style="margin-bottom: 8px;">You received this Growth Catalyst alert because you subscribed to <strong>{ticker}</strong> monitoring.</p>
        <p style="margin: 0;">
            <a href="{manage_url}" style="color: #4f46e5; text-decoration: underline; font-weight: 600;">Manage Watchlist</a> 
            &nbsp;|&nbsp; 
            <a href="{unsubscribe_url}" style="color: #e53e3e; text-decoration: underline; font-weight: 600;">Unsubscribe Completely</a>
        </p>
    </div>
</div>
"""

def send_real_email(to_email, subject, html_content):
    """
    Attempts to send a real email using SMTP environment variables.
    Returns True on success, False otherwise.
    """
    smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_username = os.environ.get("SMTP_USERNAME")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    
    # If credentials are not configured, skip real email sending
    if not smtp_username or not smtp_password:
        return False
        
    try:
        logging.info(f"Attempting to send real SMTP email to {to_email} via {smtp_server}...")
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_username
        msg["To"] = to_email
        
        part = MIMEText(html_content, "html")
        msg.attach(part)
        
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.sendmail(smtp_username, to_email, msg.as_string())
            
        logging.info(f"Real SMTP email delivered to {to_email} successfully.")
        return True
    except Exception as e:
        logging.error(f"Failed to deliver SMTP email: {e}")
        return False

def simulate_send_alert(email_address, html_content, ticker="STOCK"):
    """
    Simulates sending an email alert, or dispatches it via SMTP if configured.
    Returns: (sent_via_smtp: bool, status_message: str)
    """
    subject = f"Candlestick Sentinel Reversal Alert for {ticker}"
    
    # Try sending real email
    smtp_sent = send_real_email(email_address, subject, html_content)
    if smtp_sent:
        return True, "Email successfully delivered to your inbox via SMTP."
        
    # Fallback to local console log
    logging.info(f"[EMAIL SIMULATOR] Mock email alert dispatched to {email_address}")
    return False, "Simulated email logged to console (No SMTP credentials found)."
