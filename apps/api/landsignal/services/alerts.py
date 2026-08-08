from __future__ import annotations

from uuid import UUID

from landsignal.models import AlertRecord, AlertRuleRecord, ScoreRecord
from landsignal.settings import Settings
from landsignal.store import MemoryStore


def evaluate_rules(store: MemoryStore, score: ScoreRecord, settings: Settings) -> list[AlertRecord]:
    listing = store.listing_for_parcel(score.parcel_id)
    parcel = store.parcels[score.parcel_id]
    created: list[AlertRecord] = []
    for rule in store.alert_rules.values():
        if not rule.enabled:
            continue
        if _matches(rule.predicate, score, listing, parcel):
            channels = []
            for ch in rule.channels:
                if ch == "IN_APP":
                    channels.append("IN_APP")
                elif ch == "EMAIL":
                    channels.append("EMAIL" if settings.smtp_url else "EMAIL:NOT_CONFIGURED")
                elif ch == "SMS":
                    configured = bool(
                        settings.twilio_account_sid
                        and settings.twilio_auth_token
                        and settings.twilio_from_number
                    )
                    channels.append("SMS" if configured else "SMS:NOT_CONFIGURED")
            severity = "HIGH_CONVICTION" if score.opportunity >= 90 and score.confidence >= 80 else "STANDARD"
            title = (
                "HIGH-CONVICTION LAND SIGNAL"
                if severity == "HIGH_CONVICTION"
                else f"Alert: {rule.name}"
            )
            alert = AlertRecord(
                rule_id=rule.id,
                parcel_id=score.parcel_id,
                severity=severity,
                title=title,
                body={
                    "property": listing.title if listing else parcel.apn,
                    "price": listing.asking_price_usd if listing else None,
                    "acreage": parcel.acreage,
                    "opportunity": score.opportunity,
                    "estimated_value": score.estimated_value_usd,
                    "risk": score.risk,
                    "confidence": score.confidence,
                    "asymmetry": score.asymmetry,
                    "reason_flagged": rule.name,
                    "top_risks": score.what_could_kill[:3],
                    "freshness": listing.days_on_market if listing else None,
                    "predicate": rule.predicate,
                },
                delivered_channels=channels,
            )
            store.alerts.insert(0, alert)
            created.append(alert)
    return created


def _matches(pred: dict, score: ScoreRecord, listing, parcel) -> bool:
    checks = []
    if "opportunity_gt" in pred:
        checks.append(score.opportunity > pred["opportunity_gt"])
    if "risk_lt" in pred:
        checks.append(score.risk < pred["risk_lt"])
    if "confidence_gt" in pred:
        checks.append(score.confidence > pred["confidence_gt"])
    if "asymmetry_gt" in pred:
        checks.append(score.asymmetry > pred["asymmetry_gt"])
    if "price_lt" in pred and listing and listing.asking_price_usd is not None:
        checks.append(listing.asking_price_usd < pred["price_lt"])
    if "acres_gt" in pred and parcel.acreage is not None:
        checks.append(parcel.acreage > pred["acres_gt"])
    if "prime_farmland_gt" in pred:
        # optional — skip if unknown
        checks.append(True)
    return all(checks) if checks else False


def create_rule(store: MemoryStore, name: str, predicate: dict, channels: list[str]) -> AlertRuleRecord:
    rule = AlertRuleRecord(name=name, predicate=predicate, channels=channels)
    store.alert_rules[rule.id] = rule
    return rule
