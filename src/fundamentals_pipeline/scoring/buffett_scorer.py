"""BuffettHeuristicScorer v1 -- the first `Scorer` implementation.

Pure: `ScorerInput` in, `ScorerOutput` out. No I/O, no clock, no randomness.
`scoring/builder.py` is the only module that reads the warehouse or writes rows.

Reads only the `metrics_*` grain, never raw fundamentals and never prices, so a
future MLScorer over the same tables inherits the same no-leakage guarantee
(spec 7.1).
"""

from __future__ import annotations

from ..contracts.scorecard_schema import (
    ChecklistVerdict,
    ComponentResult,
    CriterionResult,
    ScoreBadge,
    ScoreReasonCode,
    ScorerInput,
    ScorerOutput,
)
from .config import ComponentConfig, CriterionConfig, ScorecardConfig
from .ramps import clamp_points, evaluate_checklist, evaluate_ramp

# The metric whose truth replaces the ROE criterion (spec 7.4.3). Negative book
# equity alongside a durable profit record is the book's durable-advantage
# special case, so ROE -- which is null with `negative_base` exactly then -- must
# not drag the component down.
NEGATIVE_EQUITY_METRIC = "negative_equity_strong_earnings"
NEGATIVE_EQUITY_TRUE = 1.0


def _negative_equity_applies(inp: ScorerInput) -> bool:
    """Whether the durable-negative-equity special case fires for this ticker."""
    reading = inp.reading(NEGATIVE_EQUITY_METRIC)
    return reading is not None and reading.value == NEGATIVE_EQUITY_TRUE


def _score_criterion(
    criterion: CriterionConfig,
    component: ComponentConfig,
    inp: ScorerInput,
    config: ScorecardConfig,
) -> CriterionResult:
    """Grade one criterion, or mark it not-applicable with its reason.

    A criterion is not applicable when its metric was never computed, or was
    computed to a reasoned null. Either way it contributes no points and no
    weight, and the component renormalizes around it (spec 7.4.1). The reason
    code is carried through so the UI can explain the gap rather than showing a
    blank.
    """
    override = criterion.negative_equity_override and _negative_equity_applies(inp)
    reading = inp.reading(criterion.metric_id)

    if override:
        # Full points regardless of the ROE reading, which is null by
        # construction in exactly this case.
        return CriterionResult(
            criterion_id=criterion.criterion_id,
            metric_id=criterion.metric_id,
            component_id=component.component_id,
            value=reading.value if reading is not None else None,
            points=clamp_points(config.policy.negative_equity_override_points),
            weight=None,  # assigned by the component after renormalization
            checklist_verdict=ChecklistVerdict.PASS,
            reason_code=None,
            annotation=config.policy.negative_equity_annotation,
        )

    if reading is None:
        return CriterionResult(
            criterion_id=criterion.criterion_id,
            metric_id=criterion.metric_id,
            component_id=component.component_id,
            value=None,
            points=None,
            weight=None,
            checklist_verdict=ChecklistVerdict.NOT_APPLICABLE,
            reason_code=ScoreReasonCode.NO_APPLICABLE_CRITERION,
        )

    if reading.value is None:
        return CriterionResult(
            criterion_id=criterion.criterion_id,
            metric_id=criterion.metric_id,
            component_id=component.component_id,
            value=None,
            points=None,
            weight=None,
            checklist_verdict=ChecklistVerdict.NOT_APPLICABLE,
            reason_code=reading.reason_code,
        )

    return CriterionResult(
        criterion_id=criterion.criterion_id,
        metric_id=criterion.metric_id,
        component_id=component.component_id,
        value=reading.value,
        points=clamp_points(evaluate_ramp(reading.value, criterion.ramp)),
        weight=None,
        checklist_verdict=evaluate_checklist(reading.value, criterion.checklist),
        reason_code=None,
        quality_flag=reading.quality_flag,
    )


def _score_component(
    component: ComponentConfig,
    results: list[CriterionResult],
    config: ScorecardConfig,
) -> tuple[ComponentResult, list[CriterionResult]]:
    """Average the applicable criteria, or exclude the component.

    Criteria carry even weight within a component (see the config header), so
    renormalization is a plain mean over the applicable ones -- but the assigned
    weight is written back onto each criterion so the audit trail shows what a
    criterion actually contributed after renormalization, not its nominal share.

    Excluded when no criterion applies, or when coverage falls below the
    declared floor. The floor exists because renormalizing a 30%-weight
    component onto 1 of 6 criteria is not the same component measured with less
    data; it is a different measurement wearing the same label.
    """
    total = len(component.criteria)
    applicable = [result for result in results if result.applicable]
    coverage = len(applicable) / total if total else 0.0

    if not applicable:
        return (
            ComponentResult(
                component_id=component.component_id,
                score=None,
                weight=None,
                coverage_ratio=coverage,
                applicable_criteria=0,
                total_criteria=total,
                reason_code=ScoreReasonCode.NO_APPLICABLE_CRITERION,
            ),
            results,
        )

    if coverage < config.policy.min_component_coverage:
        return (
            ComponentResult(
                component_id=component.component_id,
                score=None,
                weight=None,
                coverage_ratio=coverage,
                applicable_criteria=len(applicable),
                total_criteria=total,
                reason_code=ScoreReasonCode.COMPONENT_COVERAGE_BELOW_FLOOR,
            ),
            results,
        )

    share = 1.0 / len(applicable)
    weighted: list[CriterionResult] = []
    for result in results:
        if result.applicable:
            weighted.append(
                CriterionResult(
                    criterion_id=result.criterion_id,
                    metric_id=result.metric_id,
                    component_id=result.component_id,
                    value=result.value,
                    points=result.points,
                    weight=share,
                    checklist_verdict=result.checklist_verdict,
                    reason_code=result.reason_code,
                    annotation=result.annotation,
                    quality_flag=result.quality_flag,
                )
            )
        else:
            weighted.append(result)

    score = sum(result.points * share for result in weighted if result.applicable)
    return (
        ComponentResult(
            component_id=component.component_id,
            score=score,
            weight=None,  # assigned after top-level renormalization
            coverage_ratio=coverage,
            applicable_criteria=len(applicable),
            total_criteria=total,
        ),
        weighted,
    )


class BuffettHeuristicScorer:
    """The book's scorecard: graded ramps plus the literal checklist."""

    def __init__(self, config: ScorecardConfig) -> None:
        self._config = config
        self.name = config.scorer_name
        self.version = config.scorer_version
        self.config_hash = config.config_hash

    @property
    def config(self) -> ScorecardConfig:
        """The validated, hash-pinned configuration this scorer runs on."""
        return self._config

    def score(self, inp: ScorerInput) -> ScorerOutput:
        """Produce a full scorecard, or a reasoned null composite.

        Never returns a composite of 0 for an unmeasurable company: that would
        rank it as the worst rather than the unknown (spec 7.4, S4.5).
        """
        config = self._config
        all_criteria: list[CriterionResult] = []
        components: list[ComponentResult] = []

        for component in config.components:
            graded = [
                _score_criterion(criterion, component, inp, config)
                for criterion in component.criteria
            ]
            component_result, weighted = _score_component(component, graded, config)
            components.append(component_result)
            all_criteria.extend(weighted)

        scored = [
            (component_config, result)
            for component_config, result in zip(
                config.components, components, strict=True
            )
            if result.score is not None
        ]
        weight_total = sum(
            component_config.weight for component_config, _ in scored
        )

        if not scored or weight_total <= 0:
            return ScorerOutput(
                ticker=inp.ticker,
                as_of_year=inp.as_of_year,
                composite=None,
                reason_code=ScoreReasonCode.NO_APPLICABLE_COMPONENT,
                coverage_ratio=self._coverage_ratio(all_criteria),
                checklist_passed=self._checklist_passed(all_criteria),
                checklist_applicable=self._checklist_applicable(all_criteria),
                components=tuple(components),
                criteria=tuple(all_criteria),
                badges=self._badges(
                    inp, self._coverage_ratio(all_criteria), all_criteria
                ),
            )

        final_components: list[ComponentResult] = []
        composite = 0.0
        for component_config, result in zip(config.components, components, strict=True):
            if result.score is None:
                final_components.append(result)
                continue
            weight = component_config.weight / weight_total
            composite += result.score * weight
            final_components.append(
                ComponentResult(
                    component_id=result.component_id,
                    score=result.score,
                    weight=weight,
                    coverage_ratio=result.coverage_ratio,
                    applicable_criteria=result.applicable_criteria,
                    total_criteria=result.total_criteria,
                    reason_code=result.reason_code,
                )
            )

        coverage = self._coverage_ratio(all_criteria)
        return ScorerOutput(
            ticker=inp.ticker,
            as_of_year=inp.as_of_year,
            composite=composite,
            reason_code=None,
            coverage_ratio=coverage,
            checklist_passed=self._checklist_passed(all_criteria),
            checklist_applicable=self._checklist_applicable(all_criteria),
            components=tuple(final_components),
            criteria=tuple(all_criteria),
            badges=self._badges(inp, coverage, all_criteria),
        )

    @staticmethod
    def _coverage_ratio(criteria: list[CriterionResult]) -> float:
        """Applicable criteria over total, across the whole scorecard."""
        if not criteria:
            return 0.0
        return sum(1 for result in criteria if result.applicable) / len(criteria)

    @staticmethod
    def _checklist_passed(criteria: list[CriterionResult]) -> int:
        return sum(
            1
            for result in criteria
            if result.checklist_verdict == ChecklistVerdict.PASS
        )

    @staticmethod
    def _checklist_applicable(criteria: list[CriterionResult]) -> int:
        return sum(
            1
            for result in criteria
            if result.checklist_verdict != ChecklistVerdict.NOT_APPLICABLE
        )

    def _badges(
        self,
        inp: ScorerInput,
        coverage: float,
        criteria: list[CriterionResult],
    ) -> tuple[ScoreBadge, ...]:
        """Prominent warnings that must survive into every UI surface (D5)."""
        policy = self._config.policy
        badges: list[ScoreBadge] = []
        if coverage < policy.low_confidence_coverage:
            badges.append(ScoreBadge.LOW_CONFIDENCE)
        if (
            inp.staleness_quarters is not None
            and inp.staleness_quarters > policy.max_staleness_quarters
        ):
            badges.append(ScoreBadge.STALE_DATA)
        if any(result.quality_flag for result in criteria if result.applicable):
            badges.append(ScoreBadge.UNRELIABLE_INPUT)
        return tuple(badges)
