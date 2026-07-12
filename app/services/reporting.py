"""
Reporting & exports -- CSV, Markdown (with embedded chart references), and
multi-sheet Excel, plus the LLM-free rule-based insights/recommendations
generator. Ported from the notebook's reporting cell.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Dict, List

import pandas as pd

from app.models.schemas import CampaignStats

logger = logging.getLogger("crm_ai.reporting")


def generate_insights_and_recommendations(stats: CampaignStats, df: pd.DataFrame) -> Dict[str, List[str]]:
    insights, recommendations = [], []

    if stats.valid_leads:
        insights.append(f"{stats.valid_leads} of {stats.total_leads} leads passed validation "
                         f"({stats.valid_leads / max(stats.total_leads, 1):.0%}).")
        insights.append(f"Average lead score is {stats.avg_score:.1f}/10 with an average "
                         f"conversion probability of {stats.avg_conversion_probability:.0%}.")
        insights.append(f"Priority split - High: {stats.high_priority}, "
                         f"Medium: {stats.medium_priority}, Low: {stats.low_priority}.")

    if stats.emails_sent:
        insights.append(f"{stats.replies_received} of {stats.emails_sent} outreach emails "
                         f"got a reply ({stats.reply_rate:.0%} reply rate).")
    if stats.replies_received:
        insights.append(f"{stats.follow_ups_sent} of {stats.replies_received} replies received "
                         f"a follow-up ({stats.follow_up_rate:.0%} follow-up rate).")
        insights.append(f"Of leads that replied: {stats.converted} converted (meeting booked), "
                         f"{stats.lost} were lost (not interested/unsubscribed/spam/bounce).")
    if stats.contacted_no_reply:
        insights.append(f"{stats.contacted_no_reply} leads were contacted but have not replied yet.")

    if not df.empty and stats.converted:
        conv_by_priority = (
            df.assign(is_converted=df["outcome"] == "Converted (meeting booked)")
            .groupby("priority")["is_converted"].mean().reindex(["High", "Medium", "Low"]).fillna(0)
        )
        best_priority = conv_by_priority.idxmax()
        insights.append(f"'{best_priority}'-priority leads convert best, at {conv_by_priority.max():.0%}.")

        replied_df = df[df["reply_received"]]
        if replied_df["follow_up_sent"].nunique() > 1:
            fu_conv = (
                replied_df.assign(is_converted=replied_df["outcome"] == "Converted (meeting booked)")
                .groupby("follow_up_sent")["is_converted"].mean()
            )
            if fu_conv.get(True, 0) > fu_conv.get(False, 0):
                insights.append(f"Leads that received a follow-up converted at "
                                 f"{fu_conv.get(True, 0):.0%} vs. {fu_conv.get(False, 0):.0%} "
                                 f"without one - follow-ups are working.")

    if stats.emails_failed:
        insights.append(f"{stats.emails_failed} email(s) failed to send after retries.")

    if stats.high_priority > stats.low_priority:
        recommendations.append("Prioritize immediate outreach on High-priority leads; "
                                "consider a phone follow-up within 24 hours.")
    if stats.avg_conversion_probability < 0.4:
        recommendations.append("Overall conversion probability is low - revisit persona "
                                "targeting criteria or tighten ICP filters upstream.")
    if stats.emails_sent and stats.reply_rate < 0.3:
        recommendations.append(f"Reply rate is only {stats.reply_rate:.0%} - test alternate "
                                f"subject lines or send times to lift engagement.")
    if stats.replies_received and stats.follow_up_rate < 0.5:
        recommendations.append("Less than half of replies get a follow-up - tighten the "
                                "classification-to-follow-up trigger so warm replies aren't missed.")
    if stats.contacted_no_reply and stats.emails_sent and \
            (stats.contacted_no_reply / stats.emails_sent) > 0.4:
        recommendations.append("A large share of contacted leads haven't replied - consider a "
                                "scheduled nudge sequence for leads silent after N days.")
    if stats.emails_failed:
        recommendations.append("Investigate SMTP delivery failures (check credentials, "
                                "rate limits, and recipient domain reputation).")
    if not recommendations:
        recommendations.append("Pipeline is healthy - scale up lead volume for the next run.")

    return {"insights": insights, "recommendations": recommendations}


def export_csv(df: pd.DataFrame, path: str) -> None:
    df.to_csv(path, index=False)
    logger.info("Exported CSV -> %s", path)


def export_markdown_report(stats: CampaignStats, insights: List[str], recommendations: List[str],
                            chart_paths: Dict[str, str], report_dir: str, path: str) -> None:
    def _img(name: str, caption: str) -> str:
        if name not in chart_paths:
            return ""
        rel = os.path.relpath(chart_paths[name], start=report_dir)
        return f"![{caption}]({rel})\n*{caption}*\n"

    md_content = f"""# Campaign Report

Generated: {datetime.now(timezone.utc).isoformat()}

## Summary
- Total leads: {stats.total_leads}
- Valid leads: {stats.valid_leads}
- Rejected leads: {stats.rejected_leads}
- Emails sent: {stats.emails_sent}
- Emails failed: {stats.emails_failed}
- Average score: {stats.avg_score:.2f}
- Average conversion probability: {stats.avg_conversion_probability:.2%}

## Priority Breakdown
- High: {stats.high_priority}
- Medium: {stats.medium_priority}
- Low: {stats.low_priority}

## Outcome Funnel - What Happened to These Leads
- Replies received: {stats.replies_received} ({stats.reply_rate:.0%} of emails sent)
- Follow-ups sent: {stats.follow_ups_sent} ({stats.follow_up_rate:.0%} of replies)
- Converted (meeting booked): {stats.converted}
- Lost (not interested / unsubscribed / spam / bounce): {stats.lost}
- Contacted, no reply yet: {stats.contacted_no_reply}
- Overall conversion rate: {stats.conversion_rate:.0%}

{_img("outcome_breakdown.png", "Lead outcome breakdown - why leads converted, were lost, or are pending")}
{_img("reply_classification_breakdown.png", "What leads said when they replied")}
{_img("conversion_rate_by_priority.png", "Conversion rate by priority tier")}
{_img("outcome_by_temperature.png", "Outcome by lead temperature (cold/warm/hot)")}
{_img("score_by_outcome.png", "Lead score by outcome")}
{_img("followup_effectiveness.png", "Conversion rate with vs. without a follow-up")}
{_img("lead_score_distribution.png", "Lead score distribution")}
{_img("priority_distribution.png", "Priority distribution")}
{_img("industry_breakdown.png", "Industry breakdown")}
{_img("persona_clustering.png", "Persona clustering (top titles)")}
{_img("conversion_probability.png", "Conversion probability histogram")}
{_img("funnel.png", "Lead funnel (leads reaching each stage)")}

## Insights
{chr(10).join(f"- {i}" for i in insights)}

## Recommendations
{chr(10).join(f"- {r}" for r in recommendations)}
"""
    with open(path, "w") as f:
        f.write(md_content)
    logger.info("Exported Markdown report -> %s", path)


def export_excel_report(leads_df: pd.DataFrame, rejected_df: pd.DataFrame,
                         stats: CampaignStats, path: str) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        (leads_df if not leads_df.empty else pd.DataFrame({"note": ["no processed leads"]})) \
            .to_excel(writer, sheet_name="Leads", index=False)
        (rejected_df if not rejected_df.empty else pd.DataFrame({"note": ["no rejected leads"]})) \
            .to_excel(writer, sheet_name="Failures", index=False)
        pd.DataFrame([stats.model_dump()]).to_excel(writer, sheet_name="Analytics", index=False)

        if not leads_df.empty:
            outcome_summary = (
                leads_df.groupby(["outcome", "priority"]).size()
                .unstack(fill_value=0).reindex(columns=["High", "Medium", "Low"])
            )
            outcome_summary.to_excel(writer, sheet_name="Outcome Summary")

            replied = leads_df[leads_df["reply_received"]]
            if not replied.empty:
                replied[["lead_id", "name", "company", "response_classification",
                         "lead_temperature", "follow_up_sent", "outcome"]] \
                    .to_excel(writer, sheet_name="Replies & Follow-ups", index=False)
    logger.info("Exported Excel report -> %s", path)
