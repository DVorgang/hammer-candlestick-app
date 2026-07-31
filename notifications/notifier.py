import logging
import html
import smtplib
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
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


def format_synergy_alert_email(signal, discovery_info, token, base_url="http://localhost:8501"):
    """
    Formats a distinct, high-impact HTML email alert for Cross-Engine Synergy setups
    (when a stock previously discovered by the AI Growth Scanner forms a Hammer Buy Reversal on a pullback).
    Features an Electric Violet & Indigo Gradient Banner and AI Growth Discovery Timeline Box.
    """
    manage_url = f"{base_url}/?token={token}"
    unsubscribe_url = f"{base_url}/?token={token}&unsubscribe=true"
    
    ticker = html.escape(str(signal.get("ticker", "TICKER")))
    pattern = html.escape(str(signal.get("pattern_type", "Hammer")))
    conf = float(signal.get("confidence_score") or 88.0)
    rsi = float(signal.get("rsi_14") or 32.0)
    vol_mult = float(signal.get("vol_mult") or 1.8)
    entry_price = float(signal.get("entry_price") or signal.get("day2_close") or 0.0)
    stop_loss = float(signal.get("stop_loss") or (entry_price * 0.95))
    profit_target = float(signal.get("profit_target") or (entry_price * 1.10))
    
    # Discovery Info Context
    disc_date = html.escape(str(discovery_info.get("discovery_date") or "Recently"))
    disc_price = discovery_info.get("initial_price")
    disc_price_str = f"${float(disc_price):.2f}" if (disc_price and disc_price != "N/A") else "N/A"
    disc_score = float(discovery_info.get("growth_score") or 8.5)
    disc_cat = html.escape(str(discovery_info.get("catalyst_type") or "Growth Breakout"))
    disc_summary = html.escape(str(discovery_info.get("headline_summary") or "High-volume AI growth catalyst."))
    
    ai = signal.get("ai_analysis") or {}
    summary = html.escape(str(ai.get("headline_summary") or f"{ticker} completes Hammer reversal following post-growth pullback."))
    takeaway = html.escape(str(ai.get("plain_english_takeaway") or f"High-conviction synergy setup for {ticker} combining AI growth spark with technical Hammer entry."))
    key_drivers = "".join(f"<li>{html.escape(str(k))}</li>" for k in (ai.get("key_catalysts") or [f"Confirmed {pattern} reversal candle", f"RSI oversold rebound at {rsi:.1f}", f"Volume surge {vol_mult:.2f}x avg"]))
    risks = "".join(f"<li>{html.escape(str(r))}</li>" for r in (ai.get("risks") or ["General market volatility", "Stop-loss discipline below Day 1 low"]))

    return f"""
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #ffffff; border: 1px solid #d8b4fe; border-radius: 12px; box-shadow: 0 4px 12px rgba(168, 85, 247, 0.15); color: #1a202c;">
    
    <!-- Top Header & Banner: Electric Violet / Indigo Gradient -->
    <div style="background: linear-gradient(135deg, #2e1065 0%, #4c1d95 100%); padding: 24px; border-radius: 10px; text-align: center; margin-bottom: 20px; color: #ffffff;">
        <span style="display: inline-block; background-color: #a855f7; color: #ffffff; font-size: 11px; font-weight: 800; text-transform: uppercase; padding: 4px 12px; border-radius: 9999px; letter-spacing: 0.05em; margin-bottom: 8px;">
            ⚡ TRadar AI Cross-Engine Synergy Alert
        </span>
        <h1 style="margin: 0; font-size: 24px; font-weight: 800; color: #ffffff;">{ticker} {pattern} Buy Reversal (${entry_price:.2f})</h1>
        <p style="margin: 6px 0 0 0; font-size: 13px; color: #e9d5ff;">Originally Discovered by AI Growth Scanner • Now Forming Technical Reversal Entry</p>
    </div>

    <!-- AI Growth Discovery Timeline Context Box -->
    <div style="background-color: #faf5ff; border: 1px solid #d8b4fe; border-radius: 10px; padding: 16px; margin-bottom: 20px; font-size: 12px; color: #581c87;">
        <div style="font-weight: 800; font-size: 13px; color: #6b21a8; margin-bottom: 6px;">
            🚀 Original Growth Discovery Context (AI Score: {disc_score:.1f}/10):
        </div>
        <ul style="margin: 0; padding-left: 18px; line-height: 1.5; color: #6b21a8;">
            <li><strong>Discovery Date & Price:</strong> {disc_date} @ {disc_price_str} ({disc_cat})</li>
            <li><strong>Catalyst Summary:</strong> {disc_summary}</li>
            <li><strong>Technical Reversal Setup Today:</strong> Stock pulled back to key support & formed a confirmed <strong>{pattern} Reversal</strong> (${entry_price:.2f}) with RSI at {rsi:.1f}!</li>
        </ul>
    </div>

    <!-- Trade Blueprint Card -->
    <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 10px; padding: 18px; margin-bottom: 20px;">
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #cbd5e1; padding-bottom: 8px; margin-bottom: 12px;">
            <div style="font-size: 17px; font-weight: 800; color: #0f172a;">
                {ticker} Trade Blueprint (2:1 R/R)
            </div>
            <span style="background-color: #dcfce7; color: #15803d; font-size: 12px; font-weight: 800; padding: 3px 10px; border-radius: 9999px; border: 1px solid #bbf7d0;">
                ⚡ SYNERGY BUY ({conf:.0f}% Conf)
            </span>
        </div>
        
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 12px; font-size: 13px;">
            <tr>
                <td style="padding: 6px; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 4px; text-align: center;">
                    <span style="font-size: 11px; color: #64748b; font-weight: 700;">EST. ENTRY</span><br>
                    <strong style="color: #2563eb; font-size: 14px;">${entry_price:.2f}</strong>
                </td>
                <td style="padding: 6px; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 4px; text-align: center;">
                    <span style="font-size: 11px; color: #64748b; font-weight: 700;">STOP LOSS</span><br>
                    <strong style="color: #dc2626; font-size: 14px;">${stop_loss:.2f}</strong>
                </td>
                <td style="padding: 6px; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 4px; text-align: center;">
                    <span style="font-size: 11px; color: #64748b; font-weight: 700;">PROFIT TARGET</span><br>
                    <strong style="color: #16a34a; font-size: 14px;">${profit_target:.2f}</strong>
                </td>
            </tr>
        </table>

        <p style="margin: 0 0 10px 0; font-size: 13px; line-height: 1.5; color: #1e293b; font-weight: 600;">
            {summary}
        </p>
        <p style="margin: 0 0 4px 0; font-size: 12px; font-weight: 700; color: #15803d;">Key Technical Drivers:</p>
        <ul style="margin: 0 0 10px 0; padding-left: 18px; font-size: 12px; color: #334155; line-height: 1.4;">{key_drivers}</ul>
        
        <p style="margin: 0 0 4px 0; font-size: 12px; font-weight: 700; color: #991b1b;">Risk Factors:</p>
        <ul style="margin: 0 0 10px 0; padding-left: 18px; font-size: 12px; color: #b91c1c; line-height: 1.4;">{risks}</ul>
        
        <p style="margin: 0; font-size: 12px; line-height: 1.4; color: #334155;"><strong>Analyst Takeaway:</strong> {takeaway}</p>
    </div>
    
    <!-- Footer -->
    <div style="border-top: 1px solid #edf2f7; padding-top: 16px; text-align: center; font-size: 12px; color: #94a3b8;">
        <p style="margin-bottom: 8px;">You are receiving this high-priority TRadar Synergy Alert because a growth stock discovered by AI formed a technical Hammer Reversal.</p>
        <p style="margin: 0;">
            <a href="{manage_url}" style="color: #2563eb; text-decoration: underline; font-weight: 600;">Manage Preferences</a> 
            &nbsp;|&nbsp; 
            <a href="{unsubscribe_url}" style="color: #dc2626; text-decoration: underline; font-weight: 600;">Unsubscribe Completely</a>
        </p>
    </div>
</div>
"""


def format_technical_digest_email(signals, token, base_url="http://localhost:8501"):
    """
    Formats a single, unified HTML email digest containing multiple watchlist technical reversal signals
    (Hammer Buy Reversals & Hanging Man Risk Warnings).
    Used when 2 or more watchlist stocks trigger reversal signals simultaneously.
    """
    if not signals:
        return ""
        
    manage_url = f"{base_url}/?token={token}"
    unsubscribe_url = f"{base_url}/?token={token}&unsubscribe=true"
    
    tickers_str = ", ".join(s.get("ticker", "") for s in signals)
    
    cards_html = ""
    for idx, signal in enumerate(signals):
        ticker = html.escape(str(signal.get("ticker", "TICKER")))
        pattern = html.escape(str(signal.get("pattern_type", "Reversal")))
        conf = float(signal.get("confidence_score") or 85.0)
        rsi = float(signal.get("rsi_14") or signal.get("rsi_at_entry") or 30.0)
        vol_mult = float(signal.get("vol_mult") or signal.get("vol_mult_at_entry") or 1.5)
        day2_close = float(signal.get("day2_close") or signal.get("entry_price") or signal.get("price") or 0.0)
        
        # Self-healing fallback if price is 0.0
        if day2_close == 0.0 and ticker != "TICKER":
            try:
                import yfinance as yf
                t_data = yf.Ticker(ticker).fast_info
                day2_close = float(t_data.last_price or 0.0)
            except Exception:
                pass
        
        is_hammer = "hammer" in pattern.lower()
        badge_bg = "#dcfce7" if is_hammer else "#fee2e2"
        badge_text = "#15803d" if is_hammer else "#b91c1c"
        badge_icon = "🔨 Hammer Buy Signal" if is_hammer else "⚠️ Hanging Man Risk Warning"
        border_col = "#bbf7d0" if is_hammer else "#fca5a5"
        bg_col = "#f0fdf4" if is_hammer else "#fff5f5"
        
        ai = signal.get("ai_analysis") or {}
        summary = html.escape(str(ai.get("headline_summary") or f"{pattern} pattern detected on {ticker} with RSI {rsi:.1f}."))
        takeaway = html.escape(str(ai.get("plain_english_takeaway") or f"Monitor {ticker} for technical confirmation."))
        key_drivers = "".join(f"<li>{html.escape(str(k))}</li>" for k in (ai.get("key_catalysts") or [f"Confirmed {pattern} candlestick", f"RSI 14 at {rsi:.1f}", f"Volume at {vol_mult:.2f}x avg"]))
        risks = "".join(f"<li>{html.escape(str(r))}</li>" for r in (ai.get("risks") or ["Market volatility", "Wait for next session confirmation"]))
        
        cards_html += f"""
        <!-- Watchlist Signal Card #{idx+1} -->
        <div style="background-color: {bg_col}; border: 1px solid {border_col}; border-radius: 10px; padding: 18px; margin-bottom: 20px;">
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #cbd5e1; padding-bottom: 8px; margin-bottom: 12px;">
                <div style="font-size: 17px; font-weight: 800; color: #0f172a;">
                    {ticker} — ${day2_close:.2f}
                </div>
                <span style="background-color: {badge_bg}; color: {badge_text}; font-size: 12px; font-weight: 800; padding: 3px 10px; border-radius: 9999px; border: 1px solid {border_col};">
                    {badge_icon} ({conf:.0f}% Conf)
                </span>
            </div>
            <div style="font-size: 13px; color: #475569; margin-bottom: 10px;">
                RSI (14-Day): <strong style="color: #0f172a;">{rsi:.1f}</strong> | Volume Surge: <strong style="color: #15803d;">{vol_mult:.2f}x 20-Day MA</strong>
            </div>
            <p style="margin: 0 0 10px 0; font-size: 13px; line-height: 1.5; color: #1e293b; font-weight: 600;">
                {summary}
            </p>
            <p style="margin: 0 0 4px 0; font-size: 12px; font-weight: 700; color: #15803d;">Technical Reversal Factors:</p>
            <ul style="margin: 0 0 10px 0; padding-left: 18px; font-size: 12px; color: #334155; line-height: 1.4;">{key_drivers}</ul>
            
            <p style="margin: 0 0 4px 0; font-size: 12px; font-weight: 700; color: #991b1b;">Risk Factors & Stop-Loss:</p>
            <ul style="margin: 0 0 10px 0; padding-left: 18px; font-size: 12px; color: #b91c1c; line-height: 1.4;">{risks}</ul>
            
            <p style="margin: 0; font-size: 12px; line-height: 1.4; color: #334155;"><strong>Analyst Takeaway:</strong> {takeaway}</p>
        </div>
        """

    return f"""
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05); color: #1a202c;">
    
    <!-- Top Header & Banner -->
    <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding: 24px; border-radius: 10px; text-align: center; margin-bottom: 24px; color: #ffffff;">
        <span style="display: inline-block; background-color: #38df88; color: #0f172a; font-size: 11px; font-weight: 800; text-transform: uppercase; padding: 4px 12px; border-radius: 9999px; letter-spacing: 0.05em; margin-bottom: 8px;">
            📊 TRadar Watchlist Digest
        </span>
        <h1 style="margin: 0; font-size: 24px; font-weight: 800; color: #ffffff;">{len(signals)} Watchlist Technical Reversals</h1>
        <p style="margin: 6px 0 0 0; font-size: 13px; color: #94a3b8;">Triggered Watchlist Stocks: {tickers_str}</p>
    </div>

    {cards_html}
    
    <!-- Footer -->
    <div style="border-top: 1px solid #edf2f7; padding-top: 16px; text-align: center; font-size: 12px; color: #94a3b8;">
        <p style="margin-bottom: 8px;">You are receiving this TRadar Technical Digest because {len(signals)} stocks on your watchlist triggered reversal patterns simultaneously.</p>
        <p style="margin: 0;">
            <a href="{manage_url}" style="color: #2563eb; text-decoration: underline; font-weight: 600;">Manage Preferences</a> 
            &nbsp;|&nbsp; 
            <a href="{unsubscribe_url}" style="color: #dc2626; text-decoration: underline; font-weight: 600;">Unsubscribe Completely</a>
        </p>
    </div>
</div>
"""


def format_growth_digest_email(candidates, token, base_url="http://localhost:8501"):
    """
    Formats a single, unified HTML email digest containing up to 3 top-ranked growth catalyst setups.
    Eliminates inbox clutter by consolidating multiple breakout alerts into one email.
    """
    if not candidates:
        return ""
        
    manage_url = f"{base_url}/?token={token}"
    unsubscribe_url = f"{base_url}/?token={token}&unsubscribe=true"
    
    top_3 = candidates[:3]
    top_tickers_str = ", ".join(c.get("ticker", "") for c in top_3)
    
    cards_html = ""
    rank_labels = ["#1 TOP RANK", "#2 RANK", "#3 RANK"]
    rank_colors = ["#166534", "#1e3a8a", "#475569"]
    bg_colors = ["#f0fdf4", "#f8fafc", "#f8fafc"]
    border_colors = ["#bbf7d0", "#e2e8f0", "#e2e8f0"]
    badge_bgs = ["#dcfce7", "#e0e7ff", "#f1f5f9"]
    badge_colors = ["#166534", "#3730a3", "#334155"]
    
    for idx, item in enumerate(top_3):
        rank = rank_labels[idx] if idx < len(rank_labels) else f"#{idx+1} RANK"
        r_color = rank_colors[idx] if idx < len(rank_colors) else "#475569"
        bg_col = bg_colors[idx] if idx < len(bg_colors) else "#f8fafc"
        border_col = border_colors[idx] if idx < len(border_colors) else "#e2e8f0"
        badge_bg = badge_bgs[idx] if idx < len(badge_bgs) else "#f1f5f9"
        badge_col = badge_colors[idx] if idx < len(badge_colors) else "#334155"
        
        ticker = html.escape(str(item.get("ticker", "TICKER")))
        score = float(item.get("growth_score") or 8.0)
        cat_type = html.escape(str(item.get("catalyst_type", "Growth Catalyst")))
        summary = html.escape(str(item.get("headline_summary", "")))
        takeaway = html.escape(str(item.get("plain_english_takeaway", "")))
        vol_mult = float(item.get("vol_mult") or 1.0)
        latest_price = item.get("latest_price") or item.get("initial_price") or item.get("entry_price") or item.get("price")
        if (not latest_price or latest_price == "N/A" or float(latest_price) == 0.0) and ticker != "TICKER":
            try:
                import yfinance as yf
                latest_price = float(yf.Ticker(ticker).fast_info.last_price or 0.0)
            except Exception:
                pass
        price_str = f"${float(latest_price):.2f}" if (latest_price and latest_price != "N/A" and float(latest_price) > 0.0) else "N/A"
        
        key_cats = "".join(f"<li>{html.escape(str(k))}</li>" for k in (item.get("key_catalysts") or []))
        risks = "".join(f"<li>{html.escape(str(r))}</li>" for r in (item.get("risks") or []))
        
        # Clickable news articles for this candidate
        news_articles = item.get("news_articles") or item.get("news") or []
        news_links_html = ""
        if news_articles:
            news_rows = ""
            for article in news_articles[:3]:
                title = html.escape(str(article.get("title", "News Article")))
                link = str(article.get("link", "#"))
                news_rows += f'<div style="margin-top: 4px;"><a href="{link}" style="color: #2563eb; font-size: 12px; font-weight: 600; text-decoration: underline;" target="_blank">{title} →</a></div>'
            news_links_html = f'<div style="margin-top: 10px; padding-top: 8px; border-top: 1px dashed #cbd5e1;"><span style="font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase;">📰 Catalyst Headlines:</span>{news_rows}</div>'

        cards_html += f"""
        <!-- Candidate Card #{idx+1} -->
        <div style="background-color: {bg_col}; border: 1px solid {border_col}; border-radius: 10px; padding: 18px; margin-bottom: 20px;">
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #cbd5e1; padding-bottom: 8px; margin-bottom: 12px;">
                <div style="font-size: 17px; font-weight: 800; color: {r_color};">
                    <span style="background-color: {r_color}; color: #ffffff; font-size: 11px; font-weight: 800; padding: 2px 8px; border-radius: 4px; margin-right: 6px;">{rank}</span>
                    {ticker} — {cat_type}
                </div>
                <span style="background-color: {badge_bg}; color: {badge_col}; font-size: 12px; font-weight: 800; padding: 3px 10px; border-radius: 9999px; border: 1px solid #cbd5e1;">
                    Score: {score:.1f} / 10
                </span>
            </div>
            <div style="font-size: 13px; color: #475569; margin-bottom: 10px;">
                Stock Price: <strong style="color: #0f172a;">{price_str}</strong> | Volume Surge: <strong style="color: {r_color};">{vol_mult:.2f}x 20-Day MA</strong>
            </div>
            <p style="margin: 0 0 10px 0; font-size: 13px; line-height: 1.5; color: #1e293b; font-weight: 600;">
                {summary}
            </p>
            <p style="margin: 0 0 4px 0; font-size: 12px; font-weight: 700; color: {r_color};">Key Growth Drivers:</p>
            <ul style="margin: 0 0 10px 0; padding-left: 18px; font-size: 12px; color: #334155; line-height: 1.4;">{key_cats}</ul>
            
            <p style="margin: 0 0 4px 0; font-size: 12px; font-weight: 700; color: #991b1b;">Risks & Considerations:</p>
            <ul style="margin: 0 0 10px 0; padding-left: 18px; font-size: 12px; color: #b91c1c; line-height: 1.4;">{risks}</ul>
            
            <p style="margin: 0; font-size: 12px; line-height: 1.4; color: #334155;"><strong>Plain-English Takeaway:</strong> {takeaway}</p>
            {news_links_html}
        </div>
        """

    return f"""
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05); color: #1a202c;">
    
    <!-- Top Header & Banner -->
    <div style="background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%); padding: 24px; border-radius: 10px; text-align: center; margin-bottom: 24px; color: #ffffff;">
        <span style="display: inline-block; background-color: #818cf8; color: #0f172a; font-size: 11px; font-weight: 800; text-transform: uppercase; padding: 4px 12px; border-radius: 9999px; letter-spacing: 0.05em; margin-bottom: 8px;">
            🚀 TRadar AI Market Digest
        </span>
        <h1 style="margin: 0; font-size: 24px; font-weight: 800; color: #ffffff;">Top {len(top_3)} Market Growth Catalysts Today</h1>
        <p style="margin: 6px 0 0 0; font-size: 13px; color: #c7d2fe;">Featured Breakouts: {top_tickers_str} • Evaluated by Groq AI Llama 3.3-70B</p>
    </div>

    {cards_html}
    
    <!-- Footer -->
    <div style="border-top: 1px solid #edf2f7; padding-top: 16px; text-align: center; font-size: 12px; color: #94a3b8;">
        <p style="margin-bottom: 8px;">You are receiving this automated TRadar Market Growth Digest because you subscribed to AI Growth Catalysts.</p>
        <p style="margin: 0;">
            <a href="{manage_url}" style="color: #2563eb; text-decoration: underline; font-weight: 600;">Manage Preferences</a> 
            &nbsp;|&nbsp; 
            <a href="{unsubscribe_url}" style="color: #dc2626; text-decoration: underline; font-weight: 600;">Unsubscribe Completely</a>
        </p>
    </div>
</div>
"""

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
            <a href="{unsubscribe_url}" style="color: #e53e3e; text-decoration: underline; font-weight: 600;">Unsubscribe Completely</a>
        </p>
    </div>
</div>
"""

def format_heartbeat_digest_email(top_setups, token, base_url="http://localhost:8501"):
    """
    Formats a responsive HTML email digest for Heartbeat Volatility Expansion breakouts.
    Includes Conviction Score (0-100), Trade Blueprint (Entry, Stop-Loss, Take-Profit), 
    Trailing Lock Tip callout box, crisp SVG heart logo header, and 24/7 public TradingView/Yahoo/Finviz chart links.
    """
    if not top_setups:
        return "<p>No heartbeat setups discovered.</p>"

    manage_url = f"{base_url}/?token={token}&action=manage"
    unsubscribe_url = f"{base_url}/?token={token}&action=unsubscribe"
    top_tickers_str = ", ".join(x.get("ticker", "") for x in top_setups)

    # Crisp lightweight SVG Heart EKG Pulse Icon (0.3 KB vs 350 KB Base64 image) to prevent Gmail clipping
    logo_img_html = """
    <svg width="52" height="52" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="vertical-align: middle; margin-bottom: 6px; filter: drop-shadow(0px 4px 10px rgba(244,114,182,0.6));">
        <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" fill="#f472b6" fill-opacity="0.25" stroke="#f472b6" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M3.5 12h3.5l1.5-3 2.5 6 2-4 1.5 1h4" stroke="#ff007f" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
    """

    cards_html = ""
    for idx, item in enumerate(top_setups, 1):
        ticker = html.escape(str(item.get("ticker", "TICKER")))
        c_score = float(item.get("conviction_score") or 80.0)
        c_type = html.escape(str(item.get("catalyst_type") or "Heartbeat Surge"))
        summary = html.escape(str(item.get("headline_summary") or ""))
        takeaway = html.escape(str(item.get("plain_english_takeaway") or ""))
        badge_tag = html.escape(str(item.get("badge_tag") or "SLEEPING GIANT HEARTBEAT PULSE"))
        badge_color = html.escape(str(item.get("badge_color") or "#ff007f"))
        
        cur_price = float(item.get("latest_price") or item.get("initial_price") or item.get("entry_price") or item.get("price") or 0.0)
        if cur_price == 0.0 and ticker != "TICKER":
            try:
                import yfinance as yf
                cur_price = float(yf.Ticker(ticker).fast_info.last_price or 0.0)
            except Exception:
                pass
        change_pct = float(item.get("price_change_pct") or 0.0)
        vol_mult = float(item.get("vol_mult") or 3.0)
        bb_width = float(item.get("bb_width_pct") or 8.0)
        above_200 = bool(item.get("above_200sma", False))
        
        # Calculate Trade Blueprint Targets
        if cur_price <= 5.00:
            target_pct = 0.32  # +32% Target for Penny Microcaps
            stop_pct = 0.065   # -6.5% Stop
        else:
            target_pct = 0.20  # +20% Target for Mid/Large Caps
            stop_pct = 0.05    # -5.0% Stop
            
        entry_low = round(cur_price * 0.98, 2)
        entry_high = round(cur_price * 1.04, 2)
        take_profit = round(cur_price * (1.0 + target_pct), 2)
        stop_loss = round(cur_price * (1.0 - stop_pct), 2)
        trailing_trigger = round(cur_price * 1.15, 2)
        rr_ratio = round(target_pct / stop_pct, 1)
        
        key_cats_list = item.get("key_catalysts", [])
        key_cats = "".join(f"<li style='margin-bottom: 2px;'>{html.escape(str(c))}</li>" for c in key_cats_list) if key_cats_list else "<li>Volume Squeeze Breakout</li>"
        
        tv_link = f"https://www.tradingview.com/chart/?symbol={ticker}"
        yh_link = f"https://finance.yahoo.com/quote/{ticker}/chart"
        fz_link = f"https://finviz.com/quote.ashx?t={ticker}"
        
        cards_html += f"""
        <div style="background-color: #ffffff; border: 2px solid #f1f5f9; border-radius: 12px; padding: 20px; margin-bottom: 24px; box-shadow: 0 4px 12px rgba(0,0,0,0.04);">
            
            <!-- Card Header & Badge -->
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; border-bottom: 1px solid #f1f5f9; padding-bottom: 12px;">
                <div>
                    <span style="font-size: 22px; font-weight: 800; color: #0f172a; letter-spacing: -0.02em;">#{idx} {ticker}</span>
                    <span style="font-size: 13px; color: #64748b; margin-left: 8px;">${cur_price:.2f} ({change_pct:+.2f}%)</span>
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="background-color: {badge_color}; color: #ffffff; font-size: 10px; font-weight: 800; text-transform: uppercase; padding: 4px 10px; border-radius: 9999px; letter-spacing: 0.05em; display: inline-block;">
                        {badge_tag}
                    </span>
                    <span style="font-size: 11px; font-weight: 800; color: #059669; white-space: nowrap;">Conviction: {c_score:.1f} / 100</span>
                </div>
            </div>
            
            <!-- Quantitative Squeeze Metrics Table -->
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 14px; background-color: #f8fafc; border-radius: 8px; font-size: 12px;">
                <tr>
                    <td style="padding: 8px 12px; color: #475569;">Buying Surge: <strong style="color: #d97706;">{vol_mult:.2f}x Normal Volume 🔥</strong></td>
                    <td style="padding: 8px 12px; color: #475569;">Price Squeeze: <strong style="color: #2563eb;">Ultra-Tight ({bb_width:.1f}%) 🎯</strong></td>
                    <td style="padding: 8px 12px; color: #475569;">1-Year Trend: <strong style="color: #059669;">{"Healthy Uptrend ✅" if above_200 else "Neutral Baseline ➖"}</strong></td>
                </tr>
            </table>

            <p style="margin: 0 0 10px 0; font-size: 13px; line-height: 1.5; color: #1e293b; font-weight: 600;">
                {summary}
            </p>

            <!-- Trade Blueprint Box -->
            <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); border-radius: 8px; padding: 14px; margin-bottom: 14px; color: #ffffff;">
                <div style="font-size: 11px; font-weight: 800; text-transform: uppercase; color: #ff007f; letter-spacing: 0.05em; margin-bottom: 8px;">
                    🎯 TRadar Structured Trade Blueprint
                </div>
                <table style="width: 100%; border-collapse: collapse; font-size: 12px; color: #f8fafc; margin-bottom: 8px;">
                    <tr>
                        <td style="padding: 4px 0;"><strong>Current Market Price:</strong></td>
                        <td style="padding: 4px 0; text-align: right; color: #ffffff; font-weight: 700;">${cur_price:.2f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 4px 0;"><strong>Suggested Entry Zone:</strong></td>
                        <td style="padding: 4px 0; text-align: right; color: #38bdf8; font-weight: 700;">${entry_low:.2f} – ${entry_high:.2f} <span style="font-size: 10px; color: #94a3b8; font-weight: 400;">(Dip to Ceiling)</span></td>
                    </tr>
                    <tr>
                        <td style="padding: 4px 0;"><strong>🎯 Take-Profit Target:</strong></td>
                        <td style="padding: 4px 0; text-align: right; color: #4ade80; font-weight: 700;">${take_profit:.2f} (+{target_pct*100:.1f}%)</td>
                    </tr>
                    <tr>
                        <td style="padding: 4px 0;"><strong>🛑 Stop-Loss Protection:</strong></td>
                        <td style="padding: 4px 0; text-align: right; color: #f87171; font-weight: 700;">${stop_loss:.2f} (-{stop_pct*100:.1f}%)</td>
                    </tr>
                    <tr>
                        <td style="padding: 4px 0;"><strong>Reward-to-Risk Ratio:</strong></td>
                        <td style="padding: 4px 0; text-align: right; color: #fbbf24; font-weight: 700;">{rr_ratio:.1f} : 1</td>
                    </tr>
                </table>
                <div style="border-top: 1px dashed #334155; padding-top: 8px; font-size: 11px; color: #cbd5e1; line-height: 1.4;">
                    <strong>💡 How to Play:</strong> Buy near <strong>${cur_price:.2f}</strong> at market open, or set a limit order on a dip down to <strong>${entry_low:.2f}</strong>. Do not FOMO buy above <strong>${entry_high:.2f}</strong>.
                </div>
            </div>

            <!-- Highlighted Trailing Lock Tip Box -->
            <div style="background-color: #fdf2f8; border-left: 4px solid #db2777; padding: 10px 12px; border-radius: 4px; margin-bottom: 14px; font-size: 12px; color: #831843;">
                <strong>💡 Trailing Lock Tip:</strong> Once price reaches <strong>${trailing_trigger:.2f} (+15%)</strong>, move your stop-loss order up to <strong>${entry_low:.2f} (breakeven)</strong> to guarantee a 100% risk-free trade while riding remaining upside!
            </div>
            
            <p style="margin: 0 0 4px 0; font-size: 12px; font-weight: 700; color: #059669;">Key Catalyst Drivers:</p>
            <ul style="margin: 0 0 12px 0; padding-left: 18px; font-size: 12px; color: #334155; line-height: 1.4;">{key_cats}</ul>
            
            <p style="margin: 0 0 14px 0; font-size: 12px; line-height: 1.4; color: #334155;"><strong>Plain-English Takeaway:</strong> {takeaway}</p>
            
            <!-- 1-Click Public 24/7 Chart Action Buttons -->
            <div style="text-align: center; border-top: 1px solid #f1f5f9; padding-top: 12px;">
                <a href="{tv_link}" target="_blank" style="display: inline-block; background-color: #2563eb; color: #ffffff; font-size: 11px; font-weight: 700; text-decoration: none; padding: 6px 12px; border-radius: 6px; margin-right: 6px;">📈 TradingView Live Chart</a>
                <a href="{yh_link}" target="_blank" style="display: inline-block; background-color: #7c3aed; color: #ffffff; font-size: 11px; font-weight: 700; text-decoration: none; padding: 6px 12px; border-radius: 6px; margin-right: 6px;">📊 Yahoo Technicals</a>
                <a href="{fz_link}" target="_blank" style="display: inline-block; background-color: #059669; color: #ffffff; font-size: 11px; font-weight: 700; text-decoration: none; padding: 6px 12px; border-radius: 6px;">📰 Finviz News</a>
            </div>
        </div>
        """

    return f"""
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05); color: #1a202c;">
    
    <!-- Top Header & Banner -->
    <div style="background: linear-gradient(135deg, #831843 0%, #4c1d95 100%); padding: 24px; border-radius: 10px; text-align: center; margin-bottom: 24px; color: #ffffff;">
        <div style="margin-bottom: 6px;">
            {logo_img_html}
        </div>
        <span style="display: inline-block; background-color: #f472b6; color: #831843; font-size: 11px; font-weight: 800; text-transform: uppercase; padding: 4px 14px; border-radius: 9999px; letter-spacing: 0.05em; margin-bottom: 8px;">
            TRADAR HEARTBEAT VOLATILITY EXPANSION
        </span>
        <h1 style="margin: 0; font-size: 24px; font-weight: 800; color: #ffffff;">Top {len(top_setups)} Heartbeat Breakouts Today</h1>
        <p style="margin: 6px 0 0 0; font-size: 13px; color: #fbcfe8;">Featured Sleeping Giant Pulses: {top_tickers_str} • Groq AI Evaluated</p>
    </div>

    {cards_html}
    
    <!-- Footer -->
    <div style="border-top: 1px solid #edf2f7; padding-top: 16px; text-align: center; font-size: 12px; color: #94a3b8;">
        <p style="margin-bottom: 8px;">You are receiving this automated TRadar Heartbeat Volatility Digest because you subscribed to Heartbeat alerts.</p>
        <p style="margin: 0;">
            <a href="{manage_url}" style="color: #2563eb; text-decoration: underline; font-weight: 600;">Manage Preferences</a> 
            &nbsp;|&nbsp; 
            <a href="{unsubscribe_url}" style="color: #dc2626; text-decoration: underline; font-weight: 600;">Unsubscribe Completely</a>
        </p>
    </div>
</div>
"""

def send_real_email(to_email, subject, html_content, secondary_email=None):
    """
    Attempts to send a real email using SMTP environment variables.
    Sends to both primary to_email and optional secondary_email if provided.
    Returns True on success, False otherwise.
    """
    smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_username = os.environ.get("SMTP_USERNAME")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    smtp_from_name = os.environ.get("SMTP_FROM_NAME", "TRadar App Alerts")
    
    # If credentials are not configured, skip real email sending
    if not smtp_username or not smtp_password:
        return False
        
    recipients = [to_email]
    if secondary_email and secondary_email.strip():
        sec = secondary_email.strip()
        if sec != to_email:
            recipients.append(sec)
        
    try:
        logging.info(f"Attempting to send real SMTP email to {recipients} via {smtp_server}...")
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = formataddr((smtp_from_name, smtp_username))
        msg["To"] = ", ".join(recipients)
        
        part = MIMEText(html_content, "html")
        msg.attach(part)
        
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.sendmail(smtp_username, recipients, msg.as_string())
            
        logging.info(f"Real SMTP email delivered to {recipients} successfully.")
        return True
    except Exception as e:
        logging.error(f"Failed to deliver SMTP email to {recipients}: {e}")
        return False

def format_unified_pm_digest_email(growth_setups, heartbeat_setups, tech_signals, token, base_url="http://localhost:8501"):
    """
    Formats a single, consolidated HTML Post-Market Digest email containing Growth, Heartbeat, and Technical setups.
    """
    import html
    manage_url = f"{base_url}/?token={token}"
    unsubscribe_url = f"{base_url}/?token={token}&unsubscribe=true"

    all_tickers = list(set([s.get("ticker") for s in (growth_setups + heartbeat_setups + tech_signals) if s.get("ticker")]))
    tickers_str = ", ".join(all_tickers[:5])

    total_count = len(growth_setups) + len(heartbeat_setups) + len(tech_signals)

    cards_html = ""

    if growth_setups:
        cards_html += "<h2 style='color: #1e1b4b; font-size: 16px; margin-top: 16px; border-bottom: 2px solid #818cf8; padding-bottom: 4px;'>🚀 Market Growth Catalysts</h2>"
        for g in growth_setups[:3]:
            ticker = html.escape(str(g.get("ticker", "TICKER")))
            score = float(g.get("score") or g.get("growth_score") or 8.0)
            summary = html.escape(str(g.get("headline_summary") or "AI growth breakout setup."))
            cards_html += f"""
            <div style="background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; padding: 12px; margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; font-weight: 700;">
                    <span>🚀 {ticker}</span>
                    <span style="color: #15803d;">Score: {score:.1f}/10</span>
                </div>
                <p style="font-size: 13px; color: #334155; margin: 6px 0 0 0;">{summary}</p>
            </div>
            """

    if heartbeat_setups:
        cards_html += "<h2 style='color: #831843; font-size: 16px; margin-top: 16px; border-bottom: 2px solid #f472b6; padding-bottom: 4px;'>💓 Heartbeat Volatility Breakouts</h2>"
        for h in heartbeat_setups[:3]:
            ticker = html.escape(str(h.get("ticker", "TICKER")))
            score = float(h.get("score") or h.get("conviction_score") or 80.0)
            summary = html.escape(str(h.get("headline_summary") or "Squeeze volume expansion."))
            cards_html += f"""
            <div style="background: #fff5f7; border: 1px solid #fbcfe8; border-radius: 8px; padding: 12px; margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; font-weight: 700;">
                    <span>💓 {ticker}</span>
                    <span style="color: #be185d;">Conviction: {score:.1f}/100</span>
                </div>
                <p style="font-size: 13px; color: #334155; margin: 6px 0 0 0;">{summary}</p>
            </div>
            """

    if tech_signals:
        cards_html += "<h2 style='color: #0f172a; font-size: 16px; margin-top: 16px; border-bottom: 2px solid #64748b; padding-bottom: 4px;'>📊 Technical Watchlist Reversals</h2>"
        for t in tech_signals:
            ticker = html.escape(str(t.get("ticker", "TICKER")))
            pattern = html.escape(str(t.get("pattern_type", "Reversal")))
            entry = float(t.get("entry_price") or 0.0)
            cards_html += f"""
            <div style="background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 8px; padding: 12px; margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; font-weight: 700;">
                    <span>📊 {ticker} ({pattern})</span>
                    <span style="color: #2563eb;">Est Entry: ${entry:.2f}</span>
                </div>
            </div>
            """

    return f"""
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px;">
    <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding: 20px; border-radius: 8px; text-align: center; color: #ffffff;">
        <span style="background: #38df88; color: #0f172a; font-size: 11px; font-weight: 800; padding: 3px 10px; border-radius: 9999px; text-transform: uppercase;">
            📊 TRadar End-of-Day Digest
        </span>
        <h1 style="margin: 10px 0 0 0; font-size: 22px; font-weight: 800;">{total_count} Market Breakouts Today</h1>
        <p style="margin: 4px 0 0 0; font-size: 13px; color: #94a3b8;">Featured: {tickers_str}</p>
    </div>

    {cards_html}

    <div style="border-top: 1px solid #e2e8f0; padding-top: 14px; margin-top: 20px; text-align: center; font-size: 12px; color: #94a3b8;">
        <a href="{manage_url}" style="color: #2563eb; font-weight: 600; text-decoration: underline;">Manage Preferences</a> 
        &nbsp;|&nbsp; 
        <a href="{unsubscribe_url}" style="color: #dc2626; font-weight: 600; text-decoration: underline;">Unsubscribe</a>
    </div>
</div>
"""

def simulate_send_alert(email_address, html_content, ticker="STOCK", secondary_email=None):
    """
    Simulates sending an email alert, or dispatches it via SMTP if configured.
    Supports secondary/CC email recipient.
    Returns: (sent_via_smtp: bool, status_message: str)
    """
    subject = f"[TRadar Alert] {ticker}"
    
    recip_desc = email_address
    if secondary_email and secondary_email.strip():
        recip_desc += f" & {secondary_email.strip()}"
    
    # Try sending real email
    smtp_sent = send_real_email(email_address, subject, html_content, secondary_email=secondary_email)
    if smtp_sent:
        return True, f"Email successfully delivered to {recip_desc} via SMTP."
        
    # Fallback to local console log
    logging.info(f"[EMAIL SIMULATOR] Mock email alert dispatched to {recip_desc}")
    return False, f"Simulated email logged to console for {recip_desc} (No SMTP credentials found)."
