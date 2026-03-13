"""
loans/trust_engine.py
=====================
Computes a trust tier for each user based on repayment behaviour.

Tiers
-----
    NEW       — no completed loans
    BRONZE    — 1 loan repaid on time
    SILVER    — 2–3 loans repaid, no defaults
    GOLD      — 4+ loans repaid, avg days-early >= 0
    PLATINUM  — 6+ loans, all on time, consistent borrower

Each tier gives a loan limit multiplier and interest rate discount.
"""
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta


TIER_CONFIG = {
    "NEW":      {"multiplier": 1.0,  "rate_discount": Decimal("0.00"), "label": "New Member",  "color": "#64748b", "icon": "🌱"},
    "BRONZE":   {"multiplier": 1.3,  "rate_discount": Decimal("0.02"), "label": "Bronze",      "color": "#b45309", "icon": "🥉"},
    "SILVER":   {"multiplier": 1.6,  "rate_discount": Decimal("0.03"), "label": "Silver",      "color": "#475569", "icon": "🥈"},
    "GOLD":     {"multiplier": 2.0,  "rate_discount": Decimal("0.05"), "label": "Gold",        "color": "#d97706", "icon": "🥇"},
    "PLATINUM": {"multiplier": 3.0,  "rate_discount": Decimal("0.07"), "label": "Platinum",    "color": "#7c3aed", "icon": "💎"},
}


def get_trust_profile(user):
    """
    Returns a full trust profile dict for the user.

    Keys:
        tier, label, color, icon, multiplier, rate_discount,
        total_repaid, total_borrowed, total_defaulted,
        avg_days_early, is_returning, is_trusted, next_tier, progress_pct
    """
    from loans.models import LoanApplication

    loans         = LoanApplication.objects.filter(user=user)
    repaid_loans  = loans.filter(fully_repaid=True)
    defaulted     = loans.filter(
        fully_repaid=False,
        amount_remaining__gt=0,
        status="Funded",
        funded_at__lt=timezone.now() - timedelta(days=60),
    )

    total_repaid    = repaid_loans.count()
    total_defaulted = defaulted.count()
    total_borrowed  = sum(float(l.qualified_amount) for l in repaid_loans)

    # Average repayment speed
    early_days_list = []
    for loan in repaid_loans:
        if hasattr(loan, 'funded_at') and loan.funded_at and hasattr(loan, 'fully_repaid_at') and loan.fully_repaid_at:
            expected_end = loan.funded_at + timedelta(days=30 * (loan.repayment_period or 1))
            days_early   = (expected_end.date() - loan.fully_repaid_at.date()).days
            early_days_list.append(days_early)
    avg_days_early = sum(early_days_list) / len(early_days_list) if early_days_list else 0

    tier   = compute_trust_tier(total_repaid, total_defaulted, avg_days_early)
    config = TIER_CONFIG[tier]

    # Progress to next tier
    next_tier, progress_pct = _next_tier_progress(tier, total_repaid, total_defaulted)

    return {
        "tier":           tier,
        "label":          config["label"],
        "color":          config["color"],
        "icon":           config["icon"],
        "multiplier":     config["multiplier"],
        "rate_discount":  config["rate_discount"],
        "total_repaid":   total_repaid,
        "total_borrowed": round(total_borrowed, 2),
        "total_defaulted": total_defaulted,
        "avg_days_early": round(avg_days_early, 1),
        "is_returning":   total_repaid >= 1,
        "is_trusted":     tier in ("GOLD", "PLATINUM"),
        "next_tier":      next_tier,
        "progress_pct":   progress_pct,
    }


def compute_trust_tier(total_repaid, total_defaulted, avg_days_early):
    if total_defaulted > 0:
        return "NEW"   # Any default resets trust
    if total_repaid == 0:
        return "NEW"
    if total_repaid == 1:
        return "BRONZE"
    if total_repaid <= 3:
        return "SILVER"
    if total_repaid >= 6 and avg_days_early >= 0:
        return "PLATINUM"
    if total_repaid >= 4:
        return "GOLD"
    return "SILVER"


def apply_trust_boost(base_limit, trust_profile):
    """
    Apply trust tier multiplier to base loan limit.
    Hard cap: KES 500,000.
    """
    boosted = float(base_limit) * trust_profile["multiplier"]
    return min(boosted, 500_000)


def _next_tier_progress(current_tier, total_repaid, total_defaulted):
    """
    Returns (next_tier_label, progress_percentage_to_next_tier).
    """
    if total_defaulted > 0:
        return ("Bronze", 0)

    thresholds = [
        ("NEW",      "Bronze",   1),
        ("BRONZE",   "Silver",   2),
        ("SILVER",   "Gold",     4),
        ("GOLD",     "Platinum", 6),
        ("PLATINUM", None,       None),
    ]

    for tier, next_label, needed in thresholds:
        if tier == current_tier:
            if needed is None:
                return (None, 100)
            prev = {"NEW": 0, "BRONZE": 1, "SILVER": 2, "GOLD": 4, "PLATINUM": 6}[tier]
            progress = min(100, int((total_repaid - prev) / (needed - prev) * 100))
            return (next_label, progress)

    return (None, 100)