"""AI 预评级引擎：两级评估 + 确定性分流。

实现 docs/tech-stack/tech-stack-python.md §10 的六条原则：
1. AI 是路由器不是评委 —— 结果 authority 恒为 ADVISORY，永不进入成绩加权；
2. 边界判定用规则 —— 五条触发规则全部确定性，阈值取自 rule_profile；
3. 防锚定 —— 专家端只读风险标记，不暴露分数（由路由层保证）；
4. 可复现 —— (version_id, model_id, prompt_version, input_hash) 唯一键幂等；
5. 失败可降级 —— FAILED/SKIPPED 即「无 AI 参考」，人工流程照常；
6. 输出强校验 —— Pydantic 校验失败写 FAILED，绝不降级成自由文本。

L1 粗筛用规则提取轻量特征（章节齐备度/图表数/公式数/页数异常），覆盖全部版本；
L2 深评只在边界带与候选上跑，默认 provider 为离线启发式，配置后可切 OpenAI 兼容端点。
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from typing import Protocol

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import (
    DEFAULT_AI_RULE_VERSION,
    DEFAULT_AI_THRESHOLDS,
    RUBRIC_ITEMS,
    AIReviewStatus,
    EscalationRuleCode,
    EscalationStatus,
    EvaluationLevel,
    ReviewTaskStatus,
    RiskFlagCode,
    ScoreAuthority,
)
from app.models import (
    AIReviewRecord,
    BlobObject,
    Competition,
    Enrollment,
    ReviewEscalation,
    ReviewTask,
    ScoreRecord,
    Submission,
    SubmissionVersion,
    User,
)
from app.services import audit
from app.services.rules import compute_total, parse_rubric
from app.services.storage import get_storage

# ───────────────────── 结构化输出契约 ─────────────────────


class Evidence(BaseModel):
    page: int = Field(ge=1)
    quote: str = Field(min_length=4, max_length=300)


class DimensionScore(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    score: float = Field(ge=0, le=100)
    evidence: list[Evidence] = Field(min_length=1)


class RiskFlag(BaseModel):
    code: RiskFlagCode
    detail: str = Field(min_length=2, max_length=300)


class PreAssessment(BaseModel):
    """L2 强校验契约：每条维度分必须有至少一处证据，无证据即判无效。"""

    dimensions: list[DimensionScore] = Field(min_length=1, max_length=10)
    confidence: float = Field(ge=0, le=1)
    risk_flags: list[RiskFlag] = Field(default_factory=list)


class L1Features(BaseModel):
    char_count: int = Field(ge=0)
    page_count: int = Field(ge=1)
    section_count: int = Field(ge=0)
    figure_count: int = Field(ge=0)
    formula_count: int = Field(ge=0)
    text_extractable: bool = True


# ───────────────────── L1 规则粗筛 ─────────────────────

_SECTION_RE = re.compile(
    r"(?:^|\n)\s*(?:[一二三四五六七八九十]+[、.．]|\d+[.．])\s*"
    r"(摘要|问题重述|问题分析|模型假设|符号说明|模型建立|模型求解|"
    r"模型检验|结果分析|模型评价|结论|参考文献|附录)"
)
_FIGURE_RE = re.compile(r"图\s*\d+|Figure\s*\d+", flags=re.IGNORECASE)
_FORMULA_RE = re.compile(r"\$[^$\n]+\$|^[^\n]{0,60}[=＝][^\n]{0,120}$", flags=re.MULTILINE)

_PLAIN_TEXT_EXT = {".txt", ".md", ".csv", ".py", ".json", ".tex", ".log"}


def read_extractable_text(blob: BlobObject, max_chars: int = 200_000) -> str:
    """读取可直接提取的文本。PDF/DOCX 首版不做解析，返回空串并留给 L1 标记 OCR_REQUIRED。"""
    name = (blob.original_name or "").lower()
    ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    if ext not in _PLAIN_TEXT_EXT:
        return ""
    try:
        raw = get_storage().path_of(blob.storage_key).read_bytes()[: max_chars * 4]
        for encoding in ("utf-8", "utf-16", "gb18030"):
            try:
                return raw.decode(encoding)[:max_chars]
            except UnicodeDecodeError:
                continue
    except OSError:
        return ""
    return ""


def extract_l1(text: str, original_name: str | None = None) -> tuple[L1Features, list[RiskFlag]]:
    """纯规则粗筛，不调用任何模型。返回特征与风险标记清单。"""
    sections = set(_SECTION_RE.findall(text))
    figures = len(_FIGURE_RE.findall(text))
    formulas = len(_FORMULA_RE.findall(text))
    chars = len(text)
    pages = text.count("\f") + 1 if "\f" in text else max(1, math.ceil(chars / 1800))
    extractable = bool(text.strip())

    features = L1Features(
        char_count=chars,
        page_count=pages,
        section_count=len(sections),
        figure_count=figures,
        formula_count=formulas,
        text_extractable=extractable,
    )

    flags: list[RiskFlag] = []
    if not extractable:
        flags.append(
            RiskFlag(
                code=RiskFlagCode.OCR_REQUIRED,
                detail="文件为 PDF/DOCX 等格式，首版不解析正文，需人工核实结构完整性",
            )
        )
    else:
        if len(sections) < 4:
            flags.append(
                RiskFlag(code=RiskFlagCode.MISSING_SECTION, detail=f"仅识别到 {len(sections)} 个标准章节")
            )
        if figures == 0:
            flags.append(RiskFlag(code=RiskFlagCode.FEW_FIGURES, detail="未识别到图表编号"))
        if formulas < 2:
            flags.append(RiskFlag(code=RiskFlagCode.SPARSE_FORMULAS, detail="公式/等式数量偏少"))
        if pages < 3 or pages > 40:
            flags.append(RiskFlag(code=RiskFlagCode.PAGE_ANOMALY, detail=f"估算页数 {pages} 偏离常见区间"))
        if chars < 200:
            flags.append(RiskFlag(code=RiskFlagCode.UNUSUAL_LENGTH, detail="可提取正文过短"))
        elif chars > 60_000:
            flags.append(RiskFlag(code=RiskFlagCode.UNUSUAL_LENGTH, detail="可提取正文异常长"))
    return features, flags


# ───────────────────── 阈值与幂等 ─────────────────────


def resolve_thresholds(competition: Competition) -> tuple[dict[str, float], str]:
    """阈值来自 rule_profile.ai_thresholds，缺省回落到 constants，绝不写死在判断里。"""
    raw: dict[str, object] = {}
    profile = competition.rule_profile
    if profile is not None:
        try:
            data = json.loads(profile.rubric_json or "{}")
            if isinstance(data, dict) and isinstance(data.get("ai_thresholds"), dict):
                raw = data["ai_thresholds"]
        except json.JSONDecodeError:
            raw = {}

    merged = dict(DEFAULT_AI_THRESHOLDS)
    for key, value in raw.items():
        if key in merged:
            try:
                merged[key] = float(value)
            except (TypeError, ValueError):
                continue
    rule_version = str(raw.get("ai_rule_version") or settings.ai_rule_version or DEFAULT_AI_RULE_VERSION)
    return merged, rule_version


def compute_input_hash(
    version: SubmissionVersion,
    blob: BlobObject,
    text: str,
    prompt_version: str,
    rule_version: str,
    thresholds: dict[str, float],
) -> str:
    """输入指纹：文件字节、版本、提示词、规则版本、阈值任一变化都算新输入。"""
    payload = json.dumps(
        {
            "version_id": version.id,
            "version_no": version.version_no,
            "md5": blob.md5,
            "size": blob.size_bytes,
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "prompt_version": prompt_version,
            "rule_version": rule_version,
            "thresholds": thresholds,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def should_run_l2(
    features: L1Features, flags: list[RiskFlag], thresholds: dict[str, float]
) -> tuple[bool, str]:
    """L2 只覆盖边界带与候选：正文不足转人工核实，无风险信号不浪费预算。"""
    if not features.text_extractable or features.char_count < int(thresholds["l2_min_page_chars"]):
        return False, "正文不可提取或长度不足，转人工核实（无 AI 参考）"
    if len(flags) >= int(thresholds["l2_risk_candidate"]):
        return True, f"命中 {len(flags)} 个 L1 风险标记，进入 L2 结构化深评"
    return False, "L1 未发现风险信号，跳过 L2 以控制预算"


# ───────────────────── Provider（可插拔）─────────────────────


class AIProvider(Protocol):
    model_id: str

    async def assess(
        self, *, text: str, rubric: list[dict[str, object]], flags: list[RiskFlag]
    ) -> PreAssessment: ...


def _find_quote(text: str, keyword: str, page_hint: int = 1) -> Evidence:
    """从正文里取一段真实证据并估算页码，避免模型编造引用。"""
    lines = [ln.strip() for ln in text.splitlines() if len(ln.strip()) >= 8]
    for line in lines:
        if keyword in line:
            return Evidence(page=page_hint, quote=line[:280])
    fallback = lines[0] if lines else "正文未识别到可用片段"
    return Evidence(page=page_hint, quote=fallback[:280])


class HeuristicProvider:
    """默认离线 provider：确定性启发式，保证无 LLM 也能跑通全链路。"""

    def __init__(self, model_id: str) -> None:
        self.model_id = model_id

    async def assess(
        self, *, text: str, rubric: list[dict[str, object]], flags: list[RiskFlag]
    ) -> PreAssessment:
        keys = [str(item["key"]) for item in rubric]
        features, _ = extract_l1(text)
        structure = min(features.section_count, 8)
        formula = min(features.formula_count, 12)
        figure = min(features.figure_count, 8)
        length = min(features.char_count // 500, 20)
        penalty = min(len(flags), 6) * 3

        raw_scores = {
            "modeling": 58 + structure * 3 + formula * 2 - penalty,
            "solving": 56 + formula * 3 + figure * 2 - penalty,
            "writing": 60 + length + structure * 2 - penalty,
        }
        keywords = {"modeling": "模型", "solving": "求解", "writing": "摘要"}
        dimensions = [
            DimensionScore(
                code=key,
                score=float(max(0, min(100, raw_scores.get(key, 60)))),
                evidence=[_find_quote(text, keywords.get(key, key))],
            )
            for key in keys
        ]
        confidence = round(max(0.1, min(0.95, 0.55 + structure * 0.04 + min(figure, 5) * 0.02)), 4)
        return PreAssessment(dimensions=dimensions, confidence=confidence, risk_flags=flags)


class OpenAICompatibleProvider:
    """可选 provider：OpenAI 兼容 chat/completions + response_format=json_object。

    返回内容一律走 PreAssessment 强校验；校验失败抛异常，由 assess_version 写 FAILED 降级。
    """

    def __init__(self, model_id: str, base_url: str, api_key: str, model_name: str) -> None:
        self.model_id = model_id
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model_name = model_name

    async def assess(
        self, *, text: str, rubric: list[dict[str, object]], flags: list[RiskFlag]
    ) -> PreAssessment:
        keys = [str(item["key"]) for item in rubric]
        system = (
            "你是数学建模论文的预评级路由器，不是评委。只输出 JSON："
            '{"dimensions":[{"code":维度键,"score":0-100,"evidence":[{"page":页码,"quote":原文片段}]}],'
            '"confidence":0-1,"risk_flags":[{"code":风险码,"detail":说明}]}。'
            f"维度键必须且只能是 {keys}；每条维度分至少一段原文证据；不得编造引用。"
            "不要输出最终成绩、奖项或申诉意见。"
        )
        async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as http:
            response = await http.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model_name,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": text[:60_000]},
                    ],
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        result = PreAssessment.model_validate(json.loads(content))
        if {d.code for d in result.dimensions} != set(keys):
            raise ValueError("LLM 返回的维度集合与赛事评分细则不一致")
        return result


def get_provider() -> AIProvider:
    if settings.ai_provider == "openai_compatible":
        if not (settings.ai_base_url and settings.ai_api_key and settings.ai_model_name):
            raise ValueError("AI_PROVIDER=openai_compatible 需配置 AI_BASE_URL/AI_API_KEY/AI_MODEL_NAME")
        return OpenAICompatibleProvider(
            settings.ai_model_id, settings.ai_base_url, settings.ai_api_key, settings.ai_model_name
        )
    return HeuristicProvider(settings.ai_model_id)


# ───────────────────── 主流程：预评级 ─────────────────────


async def assess_version(
    session: AsyncSession, version_id: str, competition: Competition, actor: User
) -> AIReviewRecord:
    """对单个版本做 L1→L2 预评级，幂等复用；失败写 FAILED 不抛给调用方。"""
    version = await session.get(SubmissionVersion, version_id)
    if version is None:
        raise LookupError("版本不存在")
    blob = await session.get(BlobObject, version.blob_id)
    if blob is None:
        raise LookupError("文件对象不存在")

    rubric = parse_rubric(competition.rule_profile, RUBRIC_ITEMS)
    thresholds, rule_version = resolve_thresholds(competition)
    prompt_version = settings.ai_prompt_version
    text = read_extractable_text(blob)
    features, flags = extract_l1(text, blob.original_name)
    input_hash = compute_input_hash(version, blob, text, prompt_version, rule_version, thresholds)

    existing = (
        await session.execute(
            select(AIReviewRecord).where(
                AIReviewRecord.version_id == version_id,
                AIReviewRecord.model_id == settings.ai_model_id,
                AIReviewRecord.prompt_version == prompt_version,
                AIReviewRecord.input_hash == input_hash,
            )
        )
    ).scalar_one_or_none()
    if existing and existing.status in (AIReviewStatus.SUCCEEDED.value, AIReviewStatus.SKIPPED.value):
        return existing  # 幂等：同一输入直接返回，不重复花钱

    record = existing or AIReviewRecord(
        version_id=version_id,
        model_id=settings.ai_model_id,
        prompt_version=prompt_version,
        input_hash=input_hash,
    )
    record.authority = ScoreAuthority.ADVISORY.value
    record.rule_version = rule_version
    record.features_json = features.model_dump_json()
    record.risk_flags_json = json.dumps([f.model_dump(mode="json") for f in flags], ensure_ascii=False)
    record.evaluation_level = EvaluationLevel.L1.value
    record.status = AIReviewStatus.PENDING.value
    record.error_message = None
    if existing is None:
        session.add(record)

    run_l2, reason = should_run_l2(features, flags, thresholds)
    record.level_reason = reason
    now = datetime.now(UTC)

    if not run_l2:
        record.status = AIReviewStatus.SKIPPED.value
        record.suggested_score = None
        record.confidence = None
        record.dimension_json = None
    else:
        try:
            assessment = await get_provider().assess(text=text, rubric=rubric, flags=flags)
            record.suggested_score = compute_total(
                {d.code: d.score for d in assessment.dimensions}, rubric
            )
            record.confidence = assessment.confidence
            record.dimension_json = json.dumps(
                [d.model_dump(mode="json") for d in assessment.dimensions], ensure_ascii=False
            )
            record.evaluation_level = EvaluationLevel.L2.value
            record.status = AIReviewStatus.SUCCEEDED.value
        except (ValidationError, ValueError, httpx.HTTPError, KeyError, TypeError, json.JSONDecodeError) as exc:
            # 强校验失败即降级：保留 L1 特征与风险标记，分数留空
            record.status = AIReviewStatus.FAILED.value
            record.error_message = f"L2 评估失败，转无 AI 参考模式：{exc}"[:500]
            record.suggested_score = None
            record.confidence = None
            record.dimension_json = None

    record.assessed_at = now
    await session.flush()
    await audit.record(
        session,
        action="AI_ASSESS",
        object_type="AIReviewRecord",
        object_id=record.id,
        actor=actor,
        after={
            "version_id": version_id,
            "status": record.status,
            "level": record.evaluation_level,
            "score": record.suggested_score,
        },
        reason=reason,
    )
    return record


# ───────────────────── 主流程：确定性分流 ─────────────────────

_AWARD_CUTOFFS_DEFAULT = [85.0, 75.0, 60.0]


def _award_cutoffs(competition: Competition) -> list[float]:
    profile = competition.rule_profile
    if profile is not None:
        try:
            data = json.loads(profile.rubric_json or "{}")
            raw = data.get("award_cutoffs")
            if isinstance(raw, list) and raw:
                return [float(x) for x in raw]
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return _AWARD_CUTOFFS_DEFAULT


def _near_boundary(score: float, cutoffs: list[float], tolerance: float) -> bool:
    return any(abs(score - cutoff) <= tolerance for cutoff in cutoffs)


async def evaluate_escalations(
    session: AsyncSession, competition: Competition, actor: User
) -> list[ReviewEscalation]:
    """五条确定性规则扫描全部作品；命中即留档，不受模型判断影响。"""
    thresholds, rule_version = resolve_thresholds(competition)
    cutoffs = _award_cutoffs(competition)
    # Submission 不直接带 competition_id，须经 Enrollment 关联
    submissions = (
        await session.execute(
            select(Submission)
            .join(Enrollment, Submission.enrollment_id == Enrollment.id)
            .where(Enrollment.competition_id == competition.id)
        )
    ).scalars().all()
    created: list[ReviewEscalation] = []

    for submission in submissions:
        tasks = (
            await session.execute(
                select(ReviewTask).where(
                    ReviewTask.submission_id == submission.id,
                    ReviewTask.status == ReviewTaskStatus.SUBMITTED.value,
                )
            )
        ).scalars().all()
        score_rows = (
            await session.execute(
                select(ScoreRecord).where(
                    ScoreRecord.task_id.in_([t.id for t in tasks]),
                    ScoreRecord.is_final.is_(True),
                    ScoreRecord.authority != ScoreAuthority.ADVISORY.value,
                )
            )
        ).scalars().all()
        values = [float(s.total_score) for s in score_rows]
        if not values:
            continue
        mean = round(sum(values) / len(values), 2)

        ai: AIReviewRecord | None = None
        if submission.current_version_id:
            ai = (
                await session.execute(
                    select(AIReviewRecord)
                    .where(
                        AIReviewRecord.version_id == submission.current_version_id,
                        AIReviewRecord.status == AIReviewStatus.SUCCEEDED.value,
                    )
                    .order_by(AIReviewRecord.created_at.desc())
                )
            ).scalars().first()

        triggered: list[tuple[EscalationRuleCode, dict[str, object], str, str | None]] = []

        # SCORE_GAP：任意两位专家分差超阈值 → 第三位专家盲评
        if len(values) >= 2:
            gap = round(max(values) - min(values), 2)
            if gap > thresholds["score_gap"]:
                triggered.append(
                    (
                        EscalationRuleCode.SCORE_GAP,
                        {"scores": values, "gap": gap, "threshold": thresholds["score_gap"]},
                        "分差超阈值，追加第三位专家盲评",
                        score_rows[0].id,
                    )
                )

        # AI_HUMAN_GAP：AI 只做参考，差值超阈值时要求补充理由（不改分数）
        if ai is not None and ai.suggested_score is not None:
            gap = round(abs(mean - float(ai.suggested_score)), 2)
            if gap > thresholds["ai_human_gap"]:
                triggered.append(
                    (
                        EscalationRuleCode.AI_HUMAN_GAP,
                        {
                            "human_mean": mean,
                            "ai_reference": float(ai.suggested_score),
                            "gap": gap,
                            "threshold": thresholds["ai_human_gap"],
                        },
                        "人机评分差异显著，要求专家补充评分理由（AI 分不加权）",
                        score_rows[0].id,
                    )
                )
            if float(ai.confidence or 1) < thresholds["low_confidence"] and _near_boundary(
                mean, cutoffs, thresholds["award_boundary"]
            ):
                triggered.append(
                    (
                        EscalationRuleCode.LOW_CONFIDENCE,
                        {
                            "confidence": float(ai.confidence or 0),
                            "threshold": thresholds["low_confidence"],
                            "human_mean": mean,
                        },
                        "AI 置信度低且总分处于奖项边界，转专家组复核",
                        score_rows[0].id,
                    )
                )

        # RISK_CONFIRMED：专家评语确认了 AI 标出的风险 → 强制规范审查
        flags = json.loads(ai.risk_flags_json or "[]") if ai is not None else []
        confirmed = [
            s.id
            for s in score_rows
            if any(word in (s.comment or "") for word in ("确认", "风险", "存疑"))
        ]
        if flags and confirmed:
            triggered.append(
                (
                    EscalationRuleCode.RISK_CONFIRMED,
                    {"risk_flags": flags, "confirmed_by": confirmed},
                    "专家确认 AI 风险标记，强制复审与规范审查",
                    confirmed[0],
                )
            )

        # AWARD_BOUNDARY：总分落在奖项分界 ±N 分内 → 复审队列
        if _near_boundary(mean, cutoffs, thresholds["award_boundary"]):
            triggered.append(
                (
                    EscalationRuleCode.AWARD_BOUNDARY,
                    {"human_mean": mean, "cutoffs": cutoffs, "tolerance": thresholds["award_boundary"]},
                    "总分位于奖项边界，自动进入复审队列",
                    score_rows[0].id,
                )
            )

        for code, observed, action, score_id in triggered:
            row = ReviewEscalation(
                competition_id=competition.id,
                submission_id=submission.id,
                rule_code=code.value,
                rule_version=rule_version,
                thresholds_json=json.dumps(thresholds, sort_keys=True),
                observed_json=json.dumps(observed, ensure_ascii=False),
                action=action,
                status=EscalationStatus.OPEN.value,
                ai_review_id=ai.id if ai is not None else None,
                triggered_by_score_id=score_id,
            )
            session.add(row)
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                continue  # 同一作品同一规则只触发一次
            created.append(row)
            await audit.record(
                session,
                action="ESCALATE",
                object_type="ReviewEscalation",
                object_id=row.id,
                actor=actor,
                after={"rule": code.value, "submission_id": submission.id, "observed": observed},
                reason=action,
            )
    return created
