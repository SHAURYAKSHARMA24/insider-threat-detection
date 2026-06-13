"""Z-score anomaly scoring (Phase 5, FR4 / NFR1).

Pure, side-effect-free scoring logic. Given a single activity record and the
relevant user's baseline, this module computes a per-feature deviation score,
selects the strongest responsible feature, and builds a short explainable
reason string. It performs **no** database access and **no** severity
classification or anomaly storage -- those are Phase 6 and beyond.

Deviation scales are deliberately made comparable so a single threshold can
later apply to all three features:

* continuous features (login hour, access count) use the absolute **Z-score**;
* the categorical ``resource_type`` uses **surprisal** ``-log(probability)``,
  which yields ~0.7 for a very common resource, ~3 for a rare one, and ~6.9 for
  an unseen one -- on roughly the same scale as a Z-score.
"""
import json
import math

from app.baseline import login_time_to_hours

# Score returned by z_score when the baseline SD is 0 but the value differs:
# high enough to flag, but finite (never inf/NaN).
SD_ZERO_DEVIATION = 999.0

# Floor probability for an unseen resource type, so surprisal stays finite.
UNSEEN_RESOURCE_FLOOR = 0.001

# Deterministic tie-break order when two features share the maximum score.
FEATURE_ORDER = ["login_time", "access_count", "resource_type"]


def z_score(value, mean, sd):
    """Return the absolute Z-score ``|(value - mean) / sd|``.

    When ``sd == 0`` the Z-score is undefined; this returns ``0.0`` if the value
    equals the mean (no deviation) or :data:`SD_ZERO_DEVIATION` otherwise. The
    result is always finite -- never ``inf`` or ``NaN``.
    """
    if sd == 0:
        return 0.0 if value == mean else SD_ZERO_DEVIATION
    return abs((value - mean) / sd)


def resource_rarity(resource_type, distribution_json):
    """Convert categorical rarity into a deviation-equivalent score.

    Uses surprisal ``-log(probability)``: common resources score low, rare ones
    higher, and an unseen resource is floored at
    :data:`UNSEEN_RESOURCE_FLOOR` so the score stays high but finite.

    Args:
        resource_type: the resource category to score.
        distribution_json: JSON string of ``{category: proportion}`` (the
            ``resource_distribution_json`` produced in Phase 4).

    Returns:
        A non-negative, finite float.

    Raises:
        ValueError: if the JSON is invalid, is not an object, or contains a
            probability that is non-numeric, NaN/inf, or outside ``[0, 1]``.
    """
    try:
        distribution = json.loads(distribution_json)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"Invalid resource distribution JSON: {exc}") from exc

    if not isinstance(distribution, dict):
        raise ValueError("Resource distribution must be a JSON object of category -> proportion")

    for category, probability in distribution.items():
        if isinstance(probability, bool) or not isinstance(probability, (int, float)):
            raise ValueError(f"Invalid probability for {category!r}: {probability!r}")
        if math.isnan(probability) or math.isinf(probability) or not 0 <= probability <= 1:
            raise ValueError(f"Probability out of range for {category!r}: {probability!r}")

    probability = distribution.get(resource_type, 0.0)
    if probability <= 0:
        probability = UNSEEN_RESOURCE_FLOOR
    return -math.log(probability)


def responsible_feature(scores):
    """Return ``(feature, score)`` for the feature with the maximum deviation.

    Ties are broken by :data:`FEATURE_ORDER` (login_time > access_count >
    resource_type), achieved by only replacing the incumbent on a strictly
    greater score while iterating in that order.

    Args:
        scores: mapping of ``{"login_time", "access_count", "resource_type"}``
            to their numeric deviation scores.
    """
    best_feature, best_score = None, None
    for feature in FEATURE_ORDER:
        score = scores[feature]
        if best_score is None or score > best_score:
            best_feature, best_score = feature, score
    return best_feature, best_score


def build_anomaly_reason(scored):
    """Build a short, demo-friendly reason string for the responsible feature."""
    feature = scored["responsible_feature"]
    value = scored["responsible_value"]
    if feature == "resource_type":
        return f"Rare resource_type, score = {value:.2f}"
    return f"Abnormal {feature}, Z = {value:.2f}"


def score_record(record, baseline):
    """Score one activity record against its user's baseline.

    Args:
        record: mapping with ``login_time`` (``HH:MM``), ``access_count``,
            and ``resource_type``.
        baseline: mapping with ``average_login_time``, ``sd_login_time``,
            ``average_access_count``, ``sd_access_count``, and
            ``resource_distribution_json``.

    Returns:
        A dict with ``login_time_z``, ``access_count_z``, ``resource_type_z``,
        ``deviation_score`` (the max of the three), ``responsible_feature``,
        ``responsible_value``, and a human-readable ``reason``. No database
        access occurs.
    """
    login_hours = login_time_to_hours(record["login_time"])
    login_time_z = z_score(
        login_hours,
        float(baseline["average_login_time"]),
        float(baseline["sd_login_time"]),
    )
    access_count_z = z_score(
        float(record["access_count"]),
        float(baseline["average_access_count"]),
        float(baseline["sd_access_count"]),
    )
    resource_type_z = resource_rarity(
        str(record["resource_type"]),
        baseline["resource_distribution_json"],
    )

    scores = {
        "login_time": login_time_z,
        "access_count": access_count_z,
        "resource_type": resource_type_z,
    }
    feature, value = responsible_feature(scores)

    scored = {
        "login_time_z": login_time_z,
        "access_count_z": access_count_z,
        "resource_type_z": resource_type_z,
        "deviation_score": value,  # == max of the three feature scores
        "responsible_feature": feature,
        "responsible_value": value,
    }
    scored["reason"] = build_anomaly_reason(scored)
    return scored


def score_activity(records, baselines):
    """Batch-score records in memory (no database writes).

    Args:
        records: iterable of record mappings, each including ``user_id``.
        baselines: mapping of ``user_id`` -> baseline dict. Records whose user
            has no baseline are skipped.

    Returns:
        A list of scored dicts (as from :func:`score_record`) with ``user_id``
        added.
    """
    results = []
    for record in records:
        baseline = baselines.get(record["user_id"])
        if baseline is None:
            continue
        scored = score_record(record, baseline)
        scored["user_id"] = record["user_id"]
        results.append(scored)
    return results
