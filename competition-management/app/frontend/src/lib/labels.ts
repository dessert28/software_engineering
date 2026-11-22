/** 状态与枚举的中文映射。后端只认英文值，展示全在这里翻。 */

export const STATE_LABEL: Record<string, string> = {
  DRAFT: '草稿',
  REGISTRATION_OPEN: '报名开放',
  REGISTRATION_CLOSED: '报名截止',
  QUALIFICATION_REVIEW: '资格审核',
  RUNNING: '进行中',
  SUBMISSION_OPEN: '提交开放',
  SUBMISSION_CLOSED: '提交截止',
  REVIEWING: '评审中',
  RESULT_PENDING: '结果待发布',
  RESULT_PUBLISHED: '结果已发布',
  APPEAL: '申诉期',
  ARCHIVED: '已归档',
}

export const STATE_COLOR: Record<string, string> = {
  DRAFT: 'default',
  REGISTRATION_OPEN: 'processing',
  REGISTRATION_CLOSED: 'warning',
  QUALIFICATION_REVIEW: 'warning',
  RUNNING: 'processing',
  SUBMISSION_OPEN: 'processing',
  SUBMISSION_CLOSED: 'warning',
  REVIEWING: 'processing',
  RESULT_PENDING: 'warning',
  RESULT_PUBLISHED: 'success',
  APPEAL: 'warning',
  ARCHIVED: 'default',
}

export const ROLE_LABEL: Record<string, string> = {
  ADMIN: '管理员',
  JUDGE: '评审专家',
  TEACHER: '指导教师',
  CAPTAIN: '队长',
  MEMBER: '队员',
}

export const ENROLLMENT_LABEL: Record<string, string> = {
  PENDING: '待审核',
  APPROVED: '已通过',
  REJECTED: '已驳回',
}

export const SUBMISSION_LABEL: Record<string, string> = {
  DRAFT: '草稿',
  SUBMITTED: '已提交',
  WITHDRAWN: '已撤回',
  LOCKED: '已锁定',
}

export const TASK_LABEL: Record<string, string> = {
  ASSIGNED: '待评审',
  IN_PROGRESS: '评审中',
  SUBMITTED: '已评分',
  OVERDUE: '已逾期',
}

export const stateLabel = (s: string) => STATE_LABEL[s] ?? s
export const stateColor = (s: string) => STATE_COLOR[s] ?? 'default'
export const roleLabel = (r: string) => ROLE_LABEL[r] ?? r

export function formatBytes(n: number | null): string {
  if (n == null) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(2)} MB`
}

// ─────────────── P1/P2 新增枚举映射 ───────────────

export const NOTIFICATION_STATUS_LABEL: Record<string, string> = {
  PENDING: '待发送',
  SENT: '已发送',
  READ: '已读',
  FAILED: '发送失败',
}

export const APPEAL_STATUS_LABEL: Record<string, string> = {
  OPEN: '待处理',
  ASSIGNED: '已指派',
  ACCEPTED: '已通过',
  REJECTED: '已驳回',
  WITHDRAWN: '已撤回',
  CLOSED: '已关闭',
}

export const APPEAL_DECISION_LABEL: Record<string, string> = {
  ACCEPTED: '通过',
  REJECTED: '驳回',
  WITHDRAWN: '撤回',
  CLOSED: '关闭',
}

export const REVIEW_EXCEPTION_TYPE_LABEL: Record<string, string> = {
  OVERDUE: '评审逾期',
  REFUSAL: '拒绝评审',
  CONFLICT: '回避冲突',
  OTHER: '其他',
}

export const REVIEW_EXCEPTION_STATUS_LABEL: Record<string, string> = {
  OPEN: '待处理',
  RESOLVED: '已处理',
}

export const EXCEPTION_ACTION_LABEL: Record<string, string> = {
  REPLACE: '替换专家',
  EXTEND: '延长时限',
  MANUAL: '人工处理',
}

export const RECHECK_STATUS_LABEL: Record<string, string> = {
  PENDING: '待复核',
  IN_PROGRESS: '复核中',
  COMPLETED: '已完成',
}

export const EXPORT_STATUS_LABEL: Record<string, string> = {
  PENDING: '生成中',
  COMPLETED: '已完成',
  FAILED: '失败',
}

export const REVISION_STATUS_LABEL: Record<string, string> = {
  OPEN: '待处理',
  IN_PROGRESS: '处理中',
  COMPLETED: '已完成',
}

export const ISSUE_STATUS_LABEL: Record<string, string> = {
  OPEN: '待解决',
  RESOLVED: '已解决',
  REJECTED: '已驳回',
}

export const EXPORT_FORMAT_LABEL: Record<string, string> = {
  CSV: 'CSV',
  JSON: 'JSON',
  XLSX: 'Excel',
}

// ─────────────── AI 预评级（ADVISORY，仅供参考）───────────────

/** AIReviewOut.status：AI 评估结果状态 */
export const AI_REVIEW_STATUS_LABEL: Record<string, string> = {
  PENDING: '待评估',
  SUCCEEDED: '成功',
  FAILED: '失败',
  DEGRADED: '已降级',
  SKIPPED: '已跳过',
}

/** AIReviewOut.evaluation_level：评估级别 */
export const EVALUATION_LEVEL_LABEL: Record<string, string> = {
  L1: '规则粗筛',
  L2: '结构化深评',
}

/** EscalationOut.rule_code：复审触发规则 */
export const ESCALATION_RULE_CODE_LABEL: Record<string, string> = {
  SCORE_GAP: '专家分差',
  AI_HUMAN_GAP: '人机分差',
  LOW_CONFIDENCE: '低置信度',
  RISK_CONFIRMED: '风险确认',
  AWARD_BOUNDARY: '奖项边界',
}

/** EscalationOut.status：复审触发处理状态 */
export const ESCALATION_STATUS_LABEL: Record<string, string> = {
  OPEN: '待处理',
  RESOLVED: '已解决',
  DISMISSED: '已忽略',
}

/** risk_flags[].code：风险标记 */
export const RISK_FLAG_CODE_LABEL: Record<string, string> = {
  MISSING_SECTION: '章节缺失',
  FEW_FIGURES: '图表偏少',
  SPARSE_FORMULAS: '公式偏少',
  PAGE_ANOMALY: '页数异常',
  LOW_EVIDENCE: '证据不足',
  OCR_REQUIRED: '需人工核实',
  UNUSUAL_LENGTH: '篇幅异常',
}

/**
 * 风险提示端点专用状态：无 AI 记录时为 NONE，
 * 其余取值与 AIReviewStatus 一致，不能复用四值映射。
 */
export const AI_RISK_STATUS_LABEL: Record<string, string> = {
  NONE: '无 AI 参考',
  PENDING: '待评估',
  SUCCEEDED: '成功',
  FAILED: '失败',
  SKIPPED: '已跳过',
}
