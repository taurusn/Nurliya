"""
Business Intelligence Insights computation module.

Computes 12 insight sections from review analysis data.
Uses Redis for caching with 24h TTL.
LLM generates weekly_plan and opening_checklist.
"""

import json
from datetime import datetime, timedelta
from collections import defaultdict
from decimal import Decimal
from typing import List, Dict, Optional, Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from logging_config import get_logger
from database import (
    Review, ReviewAnalysis, RawMention,
    TaxonomyProduct, TaxonomyCategory, PlaceTaxonomy,
    AnomalyInsight, Place
)
from redis_client import get_insight, set_insight

logger = get_logger(__name__, service="insights")


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

def parse_review_date(date_str: str) -> Optional[datetime]:
    """Parse YYYY-M-D format review dates (not zero-padded)."""
    if not date_str:
        return None
    try:
        parts = date_str.split('-')
        if len(parts) == 3:
            return datetime(int(parts[0]), int(parts[1]), int(parts[2]))
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Data loader — single pass for all sections
# ---------------------------------------------------------------------------

def load_insight_data(session: Session, place_ids: List, days: int = 90,
                      start_date: Optional[str] = None, end_date: Optional[str] = None) -> dict:
    """Load all data needed for insights in one pass.

    If start_date/end_date are provided (YYYY-MM-DD), only reviews within that
    range are included. Mentions are filtered to only those linked to included reviews.
    """
    str_place_ids = [str(p) for p in place_ids]

    all_reviews = session.query(Review).filter(Review.place_id.in_(str_place_ids)).all()

    # Parse date filter bounds
    filter_start = None
    filter_end = None
    if start_date:
        try:
            filter_start = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            pass
    if end_date:
        try:
            filter_end = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        except ValueError:
            pass

    # Filter reviews by date range
    if filter_start or filter_end:
        reviews = []
        for r in all_reviews:
            rd = parse_review_date(r.review_date)
            if rd is None:
                continue
            if filter_start and rd < filter_start:
                continue
            if filter_end and rd > filter_end:
                continue
            reviews.append(r)
    else:
        reviews = all_reviews

    review_ids = [r.id for r in reviews]
    review_map = {r.id: r for r in reviews}

    analyses = []
    analysis_map = {}
    if review_ids:
        analyses = session.query(ReviewAnalysis).filter(
            ReviewAnalysis.review_id.in_(review_ids)
        ).all()
        analysis_map = {a.review_id: a for a in analyses}

    all_mentions = session.query(RawMention).filter(
        RawMention.place_id.in_(str_place_ids)
    ).all()
    # Filter mentions to only those from included reviews
    review_id_set = set(review_ids)
    if filter_start or filter_end:
        mentions = [m for m in all_mentions if m.review_id in review_id_set]
    else:
        mentions = all_mentions

    # Taxonomy products/categories
    taxonomy = None
    for pid in str_place_ids:
        taxonomy = session.query(PlaceTaxonomy).filter(
            PlaceTaxonomy.place_id == pid,
            PlaceTaxonomy.status == "active"
        ).first()
        if taxonomy:
            break

    products = {}
    categories = {}
    if taxonomy:
        for p in taxonomy.products:
            products[p.id] = p
        for c in taxonomy.categories:
            categories[c.id] = c

    anomalies = session.query(AnomalyInsight).filter(
        AnomalyInsight.place_id.in_(str_place_ids)
    ).all()

    parsed_dates = {}
    for r in reviews:
        parsed_dates[r.id] = parse_review_date(r.review_date)

    now = datetime.utcnow()
    recent_cutoff = now - timedelta(days=days)

    return {
        "reviews": reviews,
        "review_map": review_map,
        "analyses": analyses,
        "analysis_map": analysis_map,
        "mentions": mentions,
        "products": products,
        "categories": categories,
        "taxonomy": taxonomy,
        "anomalies": anomalies,
        "parsed_dates": parsed_dates,
        "recent_cutoff": recent_cutoff,
        "now": now,
        "place_ids": str_place_ids,
    }


# ---------------------------------------------------------------------------
# Section 1: Action Checklist
# ---------------------------------------------------------------------------

def compute_action_checklist(data: dict, days: int) -> dict:
    """Reviews with needs_action=True, sorted by date desc."""
    items = []
    recent_count = 0

    for a in data["analyses"]:
        if not a.needs_action:
            continue
        review = data["review_map"].get(a.review_id)
        if not review:
            continue
        review_date = data["parsed_dates"].get(review.id)
        is_recent = review_date and review_date >= data["recent_cutoff"]
        if is_recent:
            recent_count += 1
        items.append({
            "review_id": str(review.id),
            "author": review.author,
            "rating": review.rating,
            "review_date": review.review_date,
            "text": review.text,
            "action_en": a.action_en,
            "action_ar": a.action_ar,
            "summary_en": a.summary_en,
            "urgent": a.urgent,
            "sentiment": a.sentiment,
            "score": float(a.score) if a.score else None,
            "_date": review_date,
        })

    items.sort(key=lambda x: x.get("_date") or datetime.min, reverse=True)
    for item in items:
        item.pop("_date", None)

    return {"total": len(items), "recent": recent_count, "items": items[:50]}


# ---------------------------------------------------------------------------
# Section 2: Problem Products
# ---------------------------------------------------------------------------

def compute_problem_products(data: dict) -> dict:
    """Negative mentions grouped by taxonomy product."""
    product_stats = defaultdict(lambda: {"negative": 0, "total": 0, "samples": []})

    for m in data["mentions"]:
        product_id = m.resolved_product_id or m.discovered_product_id
        if not product_id:
            continue
        product_stats[product_id]["total"] += 1
        if m.sentiment == "negative":
            product_stats[product_id]["negative"] += 1
            if len(product_stats[product_id]["samples"]) < 3:
                review = data["review_map"].get(m.review_id)
                product_stats[product_id]["samples"].append({
                    "text": m.mention_text,
                    "review_date": review.review_date if review else None,
                })

    items = []
    for product_id, stats in product_stats.items():
        if stats["negative"] == 0:
            continue
        product = data["products"].get(product_id)
        if not product:
            continue
        cat_id = product.assigned_category_id or product.discovered_category_id
        category = data["categories"].get(cat_id)
        items.append({
            "product_id": str(product_id),
            "product_name": product.display_name or product.canonical_text,
            "category_name": category.display_name_en if category else None,
            "category_name_ar": category.display_name_ar if category else None,
            "negative_mentions": stats["negative"],
            "total_mentions": stats["total"],
            "negative_pct": round(stats["negative"] / stats["total"] * 100, 1),
            "avg_sentiment": float(product.avg_sentiment) if product.avg_sentiment else None,
            "sample_complaints": stats["samples"],
        })

    items.sort(key=lambda x: -x["negative_mentions"])
    return {"items": items[:20]}


# ---------------------------------------------------------------------------
# Section 3: Opening Checklist (LLM-generated)
# ---------------------------------------------------------------------------

def compute_opening_checklist(data: dict) -> dict:
    """LLM-generated daily checklist from recurring negative topics."""
    # First compute topic stats to feed to LLM
    topic_counts = defaultdict(lambda: {"total": 0, "recent": 0, "samples": [], "review_ids": []})
    for a in data["analyses"]:
        review_date = data["parsed_dates"].get(a.review_id)
        review = data["review_map"].get(a.review_id)
        for topic in (a.topics_negative or []):
            topic_counts[topic]["total"] += 1
            topic_counts[topic]["review_ids"].append(str(a.review_id))
            if review_date and review_date >= data["recent_cutoff"]:
                topic_counts[topic]["recent"] += 1
            if review and review.text and len(topic_counts[topic]["samples"]) < 2:
                topic_counts[topic]["samples"].append(review.text[:100])

    # Filter to topics with at least 3 complaints
    significant = {t: c for t, c in topic_counts.items() if c["total"] >= 3}
    if not significant:
        return {"items": [], "llm_generated": False}

    # Build context for LLM
    context_lines = []
    for topic, counts in sorted(significant.items(), key=lambda x: -x[1]["total"]):
        context_lines.append(
            f"- {topic}: {counts['total']} total complaints, {counts['recent']} recent"
        )
        for s in counts["samples"]:
            context_lines.append(f"  Example: \"{s}\"")

    try:
        from llm_client import client
        from config import VLLM_MODEL

        prompt = f"""Based on these recurring customer complaints for a Saudi cafe/restaurant, generate a daily opening checklist.

COMPLAINT DATA:
{chr(10).join(context_lines)}

Generate a JSON array of checklist items, ordered by severity (most important first).
Each item must be specific to the actual complaints — not generic advice.

Return ONLY valid JSON:
{{
  "items": [
    {{
      "topic": "complaint_topic",
      "check_item_en": "Specific actionable check in English",
      "check_item_ar": "نفس البند بالعربي",
      "severity": "high|medium|low",
      "complaint_count": N,
      "recent_count": N
    }}
  ]
}}"""

        response = client.chat.completions.create(
            model=VLLM_MODEL,
            messages=[
                {"role": "system", "content": "You are a business operations consultant for Saudi food & beverage businesses. Generate specific, actionable checklists based on real customer complaint data."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1000,
        )

        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        result = json.loads(content)
        items = result.get("items", [])

        # Ensure counts are correct from our data and add review_ids
        for item in items:
            topic = item.get("topic", "")
            if topic in significant:
                item["complaint_count"] = significant[topic]["total"]
                item["recent_count"] = significant[topic]["recent"]
                item["review_ids"] = significant[topic]["review_ids"]

        return {"items": items, "llm_generated": True}

    except Exception as e:
        logger.warning(f"LLM opening checklist failed, using fallback: {e}")
        # Fallback: static mapping
        TOPIC_CHECKS = {
            "cleanliness": {"en": "Inspect restrooms and dining area cleanliness", "ar": "فحص نظافة دورات المياه ومنطقة الطعام"},
            "wait_time": {"en": "Verify adequate staffing for expected volume", "ar": "التحقق من كفاية الموظفين للحجم المتوقع"},
            "food": {"en": "Check food preparation quality and freshness", "ar": "التحقق من جودة ونضارة الأغذية"},
            "drinks": {"en": "Test drink preparation and equipment calibration", "ar": "اختبار تحضير المشروبات ومعايرة المعدات"},
            "service": {"en": "Brief staff on service standards", "ar": "إحاطة الموظفين بمعايير الخدمة"},
            "quality": {"en": "Verify product quality standards", "ar": "التحقق من معايير جودة المنتجات"},
            "price": {"en": "Ensure menu prices are current and displayed", "ar": "التأكد من تحديث الأسعار وعرضها"},
            "atmosphere": {"en": "Check ambiance: lighting, music, temperature", "ar": "فحص الأجواء: الإضاءة والموسيقى والحرارة"},
            "parking": {"en": "Verify parking availability and signage", "ar": "التحقق من توفر المواقف واللافتات"},
            "staff": {"en": "Confirm all staff are present and presentable", "ar": "التأكد من حضور جميع الموظفين وأناقتهم"},
            "location": {"en": "Check entrance visibility and signs", "ar": "فحص وضوح المدخل ولافتات التوجيه"},
            "delivery": {"en": "Verify delivery system is operational", "ar": "التحقق من جاهزية نظام التوصيل"},
        }
        items = []
        for topic, counts in sorted(significant.items(), key=lambda x: -x[1]["total"]):
            check = TOPIC_CHECKS.get(topic)
            if not check:
                continue
            severity = "high" if counts["total"] >= 20 else "medium" if counts["total"] >= 10 else "low"
            items.append({
                "topic": topic,
                "check_item_en": check["en"],
                "check_item_ar": check["ar"],
                "complaint_count": counts["total"],
                "recent_count": counts["recent"],
                "severity": severity,
                "review_ids": counts["review_ids"],
            })
        return {"items": items, "llm_generated": False}


# ---------------------------------------------------------------------------
# Section 4: Urgent Issues
# ---------------------------------------------------------------------------

def compute_urgent_issues(data: dict, days: int) -> dict:
    """Reviews flagged as urgent, sorted by date desc."""
    items = []
    recent_count = 0

    for a in data["analyses"]:
        if not a.urgent:
            continue
        review = data["review_map"].get(a.review_id)
        if not review:
            continue
        review_date = data["parsed_dates"].get(review.id)
        is_recent = review_date and review_date >= data["recent_cutoff"]
        if is_recent:
            recent_count += 1
        items.append({
            "review_id": str(review.id),
            "author": review.author,
            "rating": review.rating,
            "review_date": review.review_date,
            "text": review.text,
            "summary_en": a.summary_en,
            "summary_ar": a.summary_ar,
            "action_en": a.action_en,
            "action_ar": a.action_ar,
            "topics_negative": a.topics_negative or [],
            "_date": review_date,
        })

    items.sort(key=lambda x: x.get("_date") or datetime.min, reverse=True)
    for item in items:
        item.pop("_date", None)

    return {"total": len(items), "recent": recent_count, "items": items[:30]}


# ---------------------------------------------------------------------------
# Section 5: Time Patterns
# ---------------------------------------------------------------------------

DAY_NAMES_EN = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday",
                4: "Friday", 5: "Saturday", 6: "Sunday"}
DAY_NAMES_AR = {0: "الاثنين", 1: "الثلاثاء", 2: "الأربعاء", 3: "الخميس",
                4: "الجمعة", 5: "السبت", 6: "الأحد"}


def compute_time_patterns(data: dict) -> dict:
    """Day-of-week + monthly trend aggregation."""
    day_stats = defaultdict(lambda: {"ratings": [], "count": 0, "negative": 0})
    month_stats = defaultdict(lambda: {"ratings": [], "count": 0, "negative": 0})

    for review in data["reviews"]:
        d = data["parsed_dates"].get(review.id)
        if not d:
            continue
        analysis = data["analysis_map"].get(review.id)

        dow = d.weekday()
        day_stats[dow]["count"] += 1
        if review.rating:
            day_stats[dow]["ratings"].append(review.rating)
        if analysis and analysis.sentiment == "negative":
            day_stats[dow]["negative"] += 1

        month_key = d.strftime("%Y-%m")
        month_stats[month_key]["count"] += 1
        if review.rating:
            month_stats[month_key]["ratings"].append(review.rating)
        if analysis and analysis.sentiment == "negative":
            month_stats[month_key]["negative"] += 1

    day_of_week = []
    for dow in range(7):
        s = day_stats[dow]
        avg_rating = round(sum(s["ratings"]) / len(s["ratings"]), 1) if s["ratings"] else None
        neg_pct = round(s["negative"] / s["count"] * 100, 1) if s["count"] > 0 else 0
        day_of_week.append({
            "day": DAY_NAMES_EN[dow],
            "day_ar": DAY_NAMES_AR[dow],
            "avg_rating": avg_rating,
            "review_count": s["count"],
            "negative_pct": neg_pct,
        })

    monthly_trend = []
    for month_key in sorted(month_stats.keys()):
        s = month_stats[month_key]
        avg_rating = round(sum(s["ratings"]) / len(s["ratings"]), 1) if s["ratings"] else None
        neg_pct = round(s["negative"] / s["count"] * 100, 1) if s["count"] > 0 else 0
        monthly_trend.append({
            "month": month_key,
            "label": datetime.strptime(month_key, "%Y-%m").strftime("%b %Y"),
            "avg_rating": avg_rating,
            "review_count": s["count"],
            "negative_pct": neg_pct,
        })

    active_days = [d for d in day_of_week if d["review_count"] > 0]
    busiest = max(active_days, key=lambda x: x["review_count"])["day"] if active_days else None
    worst = max(active_days, key=lambda x: x["negative_pct"])["day"] if active_days else None
    best_month = min(monthly_trend, key=lambda x: x["negative_pct"])["month"] if monthly_trend else None
    worst_month = max(monthly_trend, key=lambda x: x["negative_pct"])["month"] if monthly_trend else None

    return {
        "day_of_week": day_of_week,
        "monthly_trend": monthly_trend,
        "busiest_day": busiest,
        "worst_day": worst,
        "best_month": best_month,
        "worst_month": worst_month,
    }


# ---------------------------------------------------------------------------
# Section 6: Recurring Complaints
# ---------------------------------------------------------------------------

def compute_recurring_complaints(data: dict) -> dict:
    """Aggregate topics_negative across all analyses with trend detection."""
    topic_data = defaultdict(lambda: {"total": 0, "recent": 0, "dates": [], "samples": []})

    for a in data["analyses"]:
        review_date = data["parsed_dates"].get(a.review_id)
        review = data["review_map"].get(a.review_id)
        for topic in (a.topics_negative or []):
            topic_data[topic]["total"] += 1
            if review_date:
                topic_data[topic]["dates"].append(review_date)
                if review_date >= data["recent_cutoff"]:
                    topic_data[topic]["recent"] += 1
            if review and review.text and len(topic_data[topic]["samples"]) < 3:
                topic_data[topic]["samples"].append({
                    "text": review.text[:150],
                    "date": review.review_date,
                })

    total_negative = sum(1 for a in data["analyses"] if a.sentiment == "negative")

    items = []
    for topic, td in topic_data.items():
        if td["total"] < 2:
            continue
        # Trend: compare first half vs second half of dates
        sorted_dates = sorted(td["dates"])
        if len(sorted_dates) >= 4:
            mid = len(sorted_dates) // 2
            first_half = mid
            second_half = len(sorted_dates) - mid
            trend = "increasing" if second_half > first_half * 1.3 else \
                    "decreasing" if second_half < first_half * 0.7 else "stable"
        else:
            trend = "stable"

        items.append({
            "topic": topic,
            "topic_display": topic.replace("_", " ").title(),
            "count": td["total"],
            "recent_count": td["recent"],
            "trend": trend,
            "pct_of_negative": round(td["total"] / total_negative * 100, 1) if total_negative > 0 else 0,
            "sample_reviews": td["samples"],
        })

    items.sort(key=lambda x: -x["count"])
    return {"items": items}


# ---------------------------------------------------------------------------
# Section 7: Top Praised Products
# ---------------------------------------------------------------------------

def compute_top_praised(data: dict) -> dict:
    """Positive mentions grouped by taxonomy product."""
    product_stats = defaultdict(lambda: {"positive": 0, "total": 0, "samples": []})

    for m in data["mentions"]:
        product_id = m.resolved_product_id or m.discovered_product_id
        if not product_id:
            continue
        product_stats[product_id]["total"] += 1
        if m.sentiment == "positive":
            product_stats[product_id]["positive"] += 1
            if len(product_stats[product_id]["samples"]) < 3:
                review = data["review_map"].get(m.review_id)
                product_stats[product_id]["samples"].append({
                    "text": m.mention_text,
                    "review_date": review.review_date if review else None,
                })

    items = []
    for product_id, stats in product_stats.items():
        if stats["positive"] == 0:
            continue
        product = data["products"].get(product_id)
        if not product:
            continue
        cat_id = product.assigned_category_id or product.discovered_category_id
        category = data["categories"].get(cat_id)
        items.append({
            "product_id": str(product_id),
            "product_name": product.display_name or product.canonical_text,
            "category_name": category.display_name_en if category else None,
            "category_name_ar": category.display_name_ar if category else None,
            "positive_mentions": stats["positive"],
            "total_mentions": stats["total"],
            "positive_pct": round(stats["positive"] / stats["total"] * 100, 1),
            "avg_sentiment": float(product.avg_sentiment) if product.avg_sentiment else None,
            "sample_praises": stats["samples"],
        })

    items.sort(key=lambda x: -x["positive_mentions"])
    return {"items": items[:20]}


# ---------------------------------------------------------------------------
# Section 8: Satisfaction Drops
# ---------------------------------------------------------------------------

def compute_satisfaction_drops(data: dict) -> dict:
    """Pull anomaly_insights with type=drop."""
    items = []
    for a in data["anomalies"]:
        if a.anomaly_type != "drop":
            continue
        items.append({
            "id": str(a.id),
            "date": a.date,
            "topic": a.topic,
            "anomaly_type": a.anomaly_type,
            "magnitude": float(a.magnitude) if a.magnitude else None,
            "analysis": a.analysis,
            "analysis_ar": getattr(a, 'analysis_ar', None),
            "recommendation": a.recommendation,
            "recommendation_ar": getattr(a, 'recommendation_ar', None),
            "review_count": len(a.review_ids or []),
            "review_ids": [str(rid) for rid in (a.review_ids or [])],
        })
    items.sort(key=lambda x: x.get("date", ""), reverse=True)
    return {"items": items[:20]}


# ---------------------------------------------------------------------------
# Section 9: Patterns (cross-correlations)
# ---------------------------------------------------------------------------

def compute_patterns(data: dict) -> dict:
    """Day-topic correlations and monthly topic shifts."""
    # Day × Topic cross-correlation
    day_topic = defaultdict(lambda: defaultdict(int))
    topic_totals = defaultdict(int)

    for a in data["analyses"]:
        review_date = data["parsed_dates"].get(a.review_id)
        if not review_date:
            continue
        dow = DAY_NAMES_EN[review_date.weekday()]
        for topic in (a.topics_negative or []):
            day_topic[dow][topic] += 1
            topic_totals[topic] += 1

    # Find spikes: days where a topic is 2x+ average
    day_topic_correlations = []
    for day, topics in day_topic.items():
        for topic, count in topics.items():
            avg_per_day = topic_totals[topic] / 7
            if avg_per_day > 0 and count > avg_per_day * 2 and count >= 3:
                day_topic_correlations.append({
                    "day": day,
                    "topic": topic,
                    "negative_count": count,
                    "avg_per_day": round(avg_per_day, 1),
                    "multiplier": round(count / avg_per_day, 1),
                })
    day_topic_correlations.sort(key=lambda x: -x["multiplier"])

    # Monthly topic shifts: compare recent 2 months vs previous 2 months
    now = data["now"]
    recent_start = now - timedelta(days=60)
    previous_start = now - timedelta(days=120)

    recent_topics = defaultdict(lambda: {"neg": 0, "total": 0})
    previous_topics = defaultdict(lambda: {"neg": 0, "total": 0})

    for a in data["analyses"]:
        review_date = data["parsed_dates"].get(a.review_id)
        if not review_date:
            continue
        for topic in (a.topics_negative or []):
            if review_date >= recent_start:
                recent_topics[topic]["neg"] += 1
            elif review_date >= previous_start:
                previous_topics[topic]["neg"] += 1
        if review_date >= recent_start:
            for topic in (a.topics_positive or []) + (a.topics_negative or []):
                recent_topics[topic]["total"] += 1
        elif review_date >= previous_start:
            for topic in (a.topics_positive or []) + (a.topics_negative or []):
                previous_topics[topic]["total"] += 1

    monthly_topic_shifts = []
    for topic in set(list(recent_topics.keys()) + list(previous_topics.keys())):
        r = recent_topics[topic]
        p = previous_topics[topic]
        r_pct = round(r["neg"] / r["total"] * 100, 1) if r["total"] > 0 else 0
        p_pct = round(p["neg"] / p["total"] * 100, 1) if p["total"] > 0 else 0
        if r["total"] < 3 and p["total"] < 3:
            continue
        if abs(r_pct - p_pct) < 5:
            continue
        direction = "worsening" if r_pct > p_pct else "improving"
        monthly_topic_shifts.append({
            "topic": topic,
            "direction": direction,
            "recent_negative_pct": r_pct,
            "previous_negative_pct": p_pct,
            "change": round(r_pct - p_pct, 1),
        })
    monthly_topic_shifts.sort(key=lambda x: -abs(x["change"]))

    return {
        "day_topic_correlations": day_topic_correlations[:10],
        "monthly_topic_shifts": monthly_topic_shifts[:10],
    }


# ---------------------------------------------------------------------------
# Section 10: Weekly Plan (LLM-generated)
# ---------------------------------------------------------------------------

def compute_weekly_plan(data: dict, days: int) -> dict:
    """LLM-generated prioritized weekly action plan."""
    # Gather summary stats for LLM context
    urgent_count = sum(1 for a in data["analyses"] if a.urgent)
    recent_urgent = 0
    action_count = sum(1 for a in data["analyses"] if a.needs_action)
    recent_actions = 0

    for a in data["analyses"]:
        review_date = data["parsed_dates"].get(a.review_id)
        is_recent = review_date and review_date >= data["recent_cutoff"]
        if a.urgent and is_recent:
            recent_urgent += 1
        if a.needs_action and is_recent:
            recent_actions += 1

    # Top negative topics
    topic_counts = defaultdict(int)
    for a in data["analyses"]:
        for t in (a.topics_negative or []):
            topic_counts[t] += 1
    top_complaints = sorted(topic_counts.items(), key=lambda x: -x[1])[:5]

    # Problem products (top 5)
    product_neg = defaultdict(lambda: {"neg": 0, "total": 0})
    for m in data["mentions"]:
        pid = m.resolved_product_id or m.discovered_product_id
        if pid:
            product_neg[pid]["total"] += 1
            if m.sentiment == "negative":
                product_neg[pid]["neg"] += 1
    problem_prods = []
    for pid, stats in product_neg.items():
        if stats["neg"] < 2:
            continue
        p = data["products"].get(pid)
        if p:
            problem_prods.append({
                "name": p.display_name or p.canonical_text,
                "neg": stats["neg"],
                "total": stats["total"],
                "pct": round(stats["neg"] / stats["total"] * 100, 1),
            })
    problem_prods.sort(key=lambda x: -x["neg"])
    problem_prods = problem_prods[:5]

    summary = {
        "urgent_to_resolve": recent_urgent,
        "actions_pending": recent_actions,
        "top_complaint": top_complaints[0][0] if top_complaints else None,
        "problem_products_count": len(problem_prods),
    }

    # Build LLM context
    context_lines = [
        f"URGENT REVIEWS: {recent_urgent} in last {days} days ({urgent_count} total)",
        f"ACTION ITEMS: {recent_actions} in last {days} days ({action_count} total)",
        "",
        "TOP COMPLAINTS (all-time):",
    ]
    for topic, count in top_complaints:
        context_lines.append(f"  - {topic}: {count} mentions")

    if problem_prods:
        context_lines.append("")
        context_lines.append("PROBLEM PRODUCTS:")
        for pp in problem_prods:
            context_lines.append(f"  - {pp['name']}: {pp['neg']}/{pp['total']} negative ({pp['pct']}%)")

    # Recent urgent review summaries
    urgent_summaries = []
    for a in data["analyses"]:
        if not a.urgent:
            continue
        review_date = data["parsed_dates"].get(a.review_id)
        if review_date and review_date >= data["recent_cutoff"] and a.summary_en:
            urgent_summaries.append(a.summary_en)
    if urgent_summaries:
        context_lines.append("")
        context_lines.append("RECENT URGENT REVIEW SUMMARIES:")
        for s in urgent_summaries[:5]:
            context_lines.append(f"  - {s}")

    try:
        from llm_client import client
        from config import VLLM_MODEL

        prompt = f"""Generate a weekly action plan for a Saudi cafe/restaurant based on this data:

{chr(10).join(context_lines)}

Return a JSON object with:
1. A brief summary paragraph in both English and Arabic
2. A prioritized list of 3-7 action items

Return ONLY valid JSON:
{{
  "summary_en": "Brief 2-3 sentence weekly summary in English",
  "summary_ar": "ملخص أسبوعي مختصر بالعربي",
  "priorities": [
    {{
      "priority": 1,
      "type": "urgent|recurring_complaint|problem_product|action_item",
      "title_en": "Short actionable title",
      "title_ar": "عنوان قصير",
      "detail_en": "One sentence detail with specific data",
      "detail_ar": "تفاصيل بجملة واحدة مع بيانات محددة"
    }}
  ]
}}

Be specific to the data provided. Reference actual numbers and product names."""

        response = client.chat.completions.create(
            model=VLLM_MODEL,
            messages=[
                {"role": "system", "content": "You are a business consultant helping Saudi food & beverage businesses prioritize their weekly actions based on customer feedback data."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1000,
        )

        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        result = json.loads(content)
        return {
            "summary": summary,
            "summary_en": result.get("summary_en", ""),
            "summary_ar": result.get("summary_ar", ""),
            "priorities": result.get("priorities", []),
            "llm_generated": True,
        }

    except Exception as e:
        logger.warning(f"LLM weekly plan failed, using data-only summary: {e}")
        # Fallback: build priorities from raw data
        priorities = []
        p_num = 1
        if recent_urgent > 0:
            priorities.append({
                "priority": p_num,
                "type": "urgent",
                "title_en": f"Address {recent_urgent} urgent reviews",
                "title_ar": f"معالجة {recent_urgent} مراجعات عاجلة",
                "detail_en": f"{recent_urgent} urgent reviews in the last {days} days need immediate attention",
                "detail_ar": f"{recent_urgent} مراجعات عاجلة في آخر {days} يوم تحتاج اهتمام فوري",
            })
            p_num += 1
        if top_complaints:
            topic = top_complaints[0][0]
            count = top_complaints[0][1]
            priorities.append({
                "priority": p_num,
                "type": "recurring_complaint",
                "title_en": f"Address {topic.replace('_', ' ')} complaints",
                "title_ar": f"معالجة شكاوى {topic.replace('_', ' ')}",
                "detail_en": f"{topic.replace('_', ' ').title()} is the #1 complaint with {count} mentions",
                "detail_ar": f"{topic.replace('_', ' ')} هي الشكوى الأولى بـ {count} إشارة",
            })
            p_num += 1
        for pp in problem_prods[:2]:
            priorities.append({
                "priority": p_num,
                "type": "problem_product",
                "title_en": f"Review {pp['name']}",
                "title_ar": f"مراجعة {pp['name']}",
                "detail_en": f"{pp['pct']}% negative mentions ({pp['neg']}/{pp['total']})",
                "detail_ar": f"{pp['pct']}% إشارات سلبية ({pp['neg']}/{pp['total']})",
            })
            p_num += 1

        return {
            "summary": summary,
            "summary_en": "",
            "summary_ar": "",
            "priorities": priorities,
            "llm_generated": False,
        }


# ---------------------------------------------------------------------------
# Section 11: Praised Employees
# ---------------------------------------------------------------------------

def compute_praised_employees(data: dict) -> dict:
    """Staff topic mentions — positive vs negative."""
    positive_samples = []
    negative_samples = []
    staff_positive = 0
    staff_negative = 0

    for a in data["analyses"]:
        review = data["review_map"].get(a.review_id)
        if "staff" in (a.topics_positive or []):
            staff_positive += 1
            if review and review.text and len(positive_samples) < 5:
                positive_samples.append({
                    "text": review.text[:150],
                    "date": review.review_date,
                })
        if "staff" in (a.topics_negative or []):
            staff_negative += 1
            if review and review.text and len(negative_samples) < 5:
                negative_samples.append({
                    "text": review.text[:150],
                    "date": review.review_date,
                })

    total = staff_positive + staff_negative
    return {
        "staff_positive_mentions": staff_positive,
        "staff_negative_mentions": staff_negative,
        "staff_sentiment_ratio": round(staff_positive / total * 100, 1) if total > 0 else 0,
        "positive_samples": positive_samples,
        "negative_samples": negative_samples,
        "note": "Based on 'staff' topic mentions. Individual employee names are not reliably extracted.",
    }


# ---------------------------------------------------------------------------
# Section 12: Loyalty Alerts
# ---------------------------------------------------------------------------

def compute_loyalty_alerts(data: dict) -> dict:
    """Repeat customers with rating trends."""
    author_reviews = defaultdict(list)

    for review in data["reviews"]:
        if not review.author:
            continue
        d = data["parsed_dates"].get(review.id)
        if d:
            author_reviews[review.author].append({
                "date": d,
                "rating": review.rating,
                "review_id": review.id,
            })

    repeat_customers = []
    declining_count = 0
    improving_count = 0

    for author, revs in author_reviews.items():
        if len(revs) < 2:
            continue

        revs.sort(key=lambda x: x["date"])
        ratings = [r["rating"] for r in revs if r["rating"]]

        if len(ratings) >= 2:
            mid = max(1, len(ratings) // 2)
            first_avg = sum(ratings[:mid]) / mid
            second_avg = sum(ratings[mid:]) / (len(ratings) - mid)
            if second_avg < first_avg - 0.5:
                trend = "declining"
                declining_count += 1
            elif second_avg > first_avg + 0.5:
                trend = "improving"
                improving_count += 1
            else:
                trend = "stable"
        else:
            trend = "stable"

        latest_analysis = data["analysis_map"].get(revs[-1]["review_id"])
        latest_sentiment = latest_analysis.sentiment if latest_analysis else None

        alert = None
        if trend == "declining":
            alert = "Loyal customer showing declining satisfaction"

        repeat_customers.append({
            "author": author,
            "review_count": len(revs),
            "first_review": revs[0]["date"].strftime("%Y-%m-%d"),
            "latest_review": revs[-1]["date"].strftime("%Y-%m-%d"),
            "avg_rating": round(sum(ratings) / len(ratings), 1) if ratings else None,
            "rating_trend": trend,
            "ratings": ratings,
            "latest_sentiment": latest_sentiment,
            "alert": alert,
        })

    # Sort: declining first, then by review count
    repeat_customers.sort(key=lambda x: (0 if x["rating_trend"] == "declining" else 1, -x["review_count"]))

    return {
        "repeat_customers": repeat_customers[:30],
        "total_repeat_customers": len(repeat_customers),
        "declining_count": declining_count,
        "improving_count": improving_count,
    }


# ---------------------------------------------------------------------------
# Section registry & orchestrator
# ---------------------------------------------------------------------------

SECTION_FUNCTIONS = {
    "action_checklist": lambda data, days: compute_action_checklist(data, days),
    "problem_products": lambda data, days: compute_problem_products(data),
    "opening_checklist": lambda data, days: compute_opening_checklist(data),
    "urgent_issues": lambda data, days: compute_urgent_issues(data, days),
    "time_patterns": lambda data, days: compute_time_patterns(data),
    "recurring_complaints": lambda data, days: compute_recurring_complaints(data),
    "top_praised": lambda data, days: compute_top_praised(data),
    "satisfaction_drops": lambda data, days: compute_satisfaction_drops(data),
    "patterns": lambda data, days: compute_patterns(data),
    "weekly_plan": lambda data, days: compute_weekly_plan(data, days),
    "praised_employees": lambda data, days: compute_praised_employees(data),
    "loyalty_alerts": lambda data, days: compute_loyalty_alerts(data),
}

ALL_SECTIONS = list(SECTION_FUNCTIONS.keys())


def get_insights(session: Session, place_ids: List, sections: Optional[List[str]] = None,
                 days: int = 90, start_date: Optional[str] = None, end_date: Optional[str] = None) -> dict:
    """
    Main entry point for the API. Checks Redis cache first, computes on miss.

    Args:
        session: SQLAlchemy session
        place_ids: List of place UUIDs (as strings)
        sections: Optional list of section names to include
        days: Time window for recent data
        start_date: Optional YYYY-MM-DD filter start
        end_date: Optional YYYY-MM-DD filter end
    """
    requested = sections or ALL_SECTIONS
    place_id_str = str(place_ids[0])

    # Include date range in cache key so different periods are cached separately
    cache_suffix = ""
    if start_date or end_date:
        cache_suffix = f":{start_date or 'all'}:{end_date or 'all'}"

    # Try cache for each section
    result = {}
    missing_sections = []
    for section in requested:
        if section not in SECTION_FUNCTIONS:
            continue
        cached = get_insight(place_id_str, section + cache_suffix)
        if cached is not None:
            result[section] = cached
        else:
            missing_sections.append(section)

    # Compute missing sections
    if missing_sections:
        data = load_insight_data(session, place_ids, days,
                                 start_date=start_date, end_date=end_date)

        for section in missing_sections:
            try:
                section_data = SECTION_FUNCTIONS[section](data, days)
                result[section] = section_data
                # Cache it (with date-range suffix)
                set_insight(place_id_str, section + cache_suffix, section_data)
            except Exception as e:
                logger.warning(f"Failed to compute insight section {section}: {e}")
                result[section] = {"error": str(e), "items": []}

        # Build data summary from loaded data
        date_values = [d for d in data["parsed_dates"].values() if d]
        place = session.query(Place).filter(Place.id == place_ids[0]).first()

        data_summary = {
            "total_reviews": len(data["reviews"]),
            "analyzed_reviews": len(data["analyses"]),
            "total_mentions": len(data["mentions"]),
            "date_range": {
                "from": min(date_values).strftime("%Y-%m-%d") if date_values else None,
                "to": max(date_values).strftime("%Y-%m-%d") if date_values else None,
            },
        }
        if start_date:
            data_summary["filter_start"] = start_date
        if end_date:
            data_summary["filter_end"] = end_date

        result["data_summary"] = data_summary
        set_insight(place_id_str, "_data_summary" + cache_suffix, data_summary)
        result["place_name"] = place.name if place else None
        set_insight(place_id_str, "_place_name", place.name if place else None)
    else:
        # All from cache — still need metadata
        cached_summary = get_insight(place_id_str, "_data_summary" + cache_suffix)
        cached_name = get_insight(place_id_str, "_place_name")
        if cached_summary:
            result["data_summary"] = cached_summary
        else:
            # Fallback: load minimal data for summary
            from database import Review, ReviewAnalysis, RawMention
            review_count = session.query(Review).filter(Review.place_id.in_(place_ids)).count()
            analysis_count = session.query(ReviewAnalysis).join(Review).filter(Review.place_id.in_(place_ids)).count()
            mention_count = session.query(RawMention).filter(RawMention.place_id.in_(place_ids)).count()
            result["data_summary"] = {
                "total_reviews": review_count,
                "analyzed_reviews": analysis_count,
                "total_mentions": mention_count,
                "date_range": {"from": None, "to": None},
            }
        if cached_name:
            result["place_name"] = cached_name
        else:
            place = session.query(Place).filter(Place.id == place_ids[0]).first()
            result["place_name"] = place.name if place else None

    result["place_id"] = place_id_str
    result["generated_at"] = datetime.utcnow().isoformat()

    return result


def generate_all_insights(session: Session, place_ids: List, days: int = 90):
    """
    Pre-compute all insights and cache in Redis.
    Called from worker after analysis completes.
    """
    place_id_str = str(place_ids[0])
    logger.info(f"Pre-computing all insights for place {place_id_str}")

    data = load_insight_data(session, place_ids, days)

    for section, fn in SECTION_FUNCTIONS.items():
        try:
            section_data = fn(data, days)
            set_insight(place_id_str, section, section_data)
            logger.debug(f"Cached insight section: {section}")
        except Exception as e:
            logger.warning(f"Failed to pre-compute {section}: {e}")
