"""Admin API endpoints for operator job monitoring and metrics."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.models.base import get_db
from app.models.entities import Campaign, CostLog, Video

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/jobs", response_class=HTMLResponse)
def list_jobs(
    token: str = Query(..., description="Admin secret access token"),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Render an HTML dashboard table of all campaign jobs."""
    if token != settings.ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Invalid admin token",
        )

    campaigns = db.query(Campaign).order_by(Campaign.id.desc()).all()

    rows_html = []
    for c in campaigns:
        biz_name = c.business.name if c.business else f"Business #{c.business_id}"
        biz_phone = c.business.phone_e164 if c.business else ""
        biz_display = f"{biz_name} ({biz_phone})" if biz_phone else biz_name

        # Calculate total cost from CostLog
        cost_logs = db.query(CostLog).filter(CostLog.campaign_id == c.id).all()
        total_cost_inr = sum(log.est_cost_inr for log in cost_logs)
        cost_str = f"₹{total_cost_inr:.2f}"

        # Duration from video if available
        latest_video = (
            db.query(Video)
            .filter(Video.campaign_id == c.id)
            .order_by(Video.version.desc())
            .first()
        )
        duration_str = f"{latest_video.duration_s:.1f}s" if latest_video and latest_video.duration_s else "-"

        # Error message if any step failed
        step_errors = [s.error for s in c.steps if s.error]
        error_str = step_errors[-1] if step_errors else "-"

        badge_class = "badge-pending"
        if c.state in ("AWAITING_APPROVAL", "APPROVED"):
            badge_class = "badge-success"
        elif c.state == "FAILED":
            badge_class = "badge-failed"

        rows_html.append(
            f"<tr>"
            f"<td>{c.id}</td>"
            f"<td>{biz_display}</td>"
            f"<td><span class='badge {badge_class}'>{c.state}</span></td>"
            f"<td>{duration_str}</td>"
            f"<td>{cost_str}</td>"
            f"<td><code>{error_str}</code></td>"
            f"</tr>"
        )

    rows_joined = "\n".join(rows_html) if rows_html else "<tr><td colspan='6'>No jobs recorded yet.</td></tr>"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Reelwala Admin - Jobs Dashboard</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 2rem;
            background: #f8fafc;
            color: #0f172a;
        }}
        h1 {{ margin-bottom: 1.5rem; }}
        table {{
            border-collapse: collapse;
            width: 100%;
            background: #ffffff;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            border-radius: 8px;
            overflow: hidden;
        }}
        th, td {{
            padding: 12px 16px;
            text-align: left;
            border-bottom: 1px solid #e2e8f0;
        }}
        th {{
            background: #f1f5f9;
            font-weight: 600;
            color: #334155;
        }}
        tr:hover {{ background: #f8fafc; }}
        .badge {{
            display: inline-block;
            padding: 3px 10px;
            border-radius: 9999px;
            font-size: 0.85rem;
            font-weight: 600;
        }}
        .badge-success {{ background: #dcfce7; color: #15803d; }}
        .badge-failed {{ background: #fee2e2; color: #b91c1c; }}
        .badge-pending {{ background: #fef3c7; color: #b45309; }}
        code {{
            color: #ef4444;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <h1>Campaign Jobs</h1>
    <table>
        <thead>
            <tr>
                <th>Campaign ID</th>
                <th>Business</th>
                <th>State</th>
                <th>Duration</th>
                <th>Cost</th>
                <th>Error</th>
            </tr>
        </thead>
        <tbody>
            {rows_joined}
        </tbody>
    </table>
</body>
</html>
"""
    return HTMLResponse(content=html_content)
