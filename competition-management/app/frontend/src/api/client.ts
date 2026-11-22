/**
 * 接口客户端。
 *
 * 只有这一层碰 fetch 与 token；页面组件不直接写 URL。
 * token 存 localStorage，401 时统一清掉并回登录页。
 */

export interface User {
  id: string
  email: string
  name: string
  role: 'ADMIN' | 'JUDGE' | 'TEACHER' | 'CAPTAIN' | 'MEMBER'
  school: string | null
  is_active: boolean
  can_review: boolean
  expertise: string | null
}

export interface Competition {
  id: string
  title: string
  edition: string | null
  organizer: string | null
  description: string | null
  state: string
  registration_opens_at: string | null
  registration_closes_at: string | null
  submission_opens_at: string | null
  submission_closes_at: string | null
  min_team_size: number
  max_team_size: number
  rule_profile_id: string | null
}

export interface TeamMemberRow {
  id: string
  user_id: string
  role_in_team: string
  name: string | null
  email: string | null
}

export interface Team {
  id: string
  competition_id: string
  name: string
  school: string | null
  invite_code: string | null
  members: TeamMemberRow[]
}

export interface Enrollment {
  id: string
  competition_id: string
  team_id: string
  status: string
  review_comment: string | null
}

export interface Submission {
  id: string
  enrollment_id: string
  status: string
  current_version_id: string | null
  submitted_at: string | null
  versions: SubmissionVersion[]
}

export interface SubmissionVersion {
  id: string
  version_no: number
  blob_id: string
  note: string | null
  created_at: string
}

export interface ReviewTask {
  id: string
  competition_id: string
  submission_id: string
  reviewer_id: string
  status: string
  material_ref: string
  due_at: string | null
}

export interface AnonymousMaterial {
  task_id: string
  competition_title: string
  problem_code: string
  version_no: number
  file_name: string | null
  file_size: number | null
  note: string | null
  rubric: { key: string; label: string; weight: number }[]
}

export interface ResultRow {
  id: string
  competition_id: string
  team_id: string
  team_name: string
  final_score: number | null
  rank: number | null
  award: string | null
  status: string
  review_count: number
}

export interface AuditRow {
  id: string
  action: string
  object_type: string
  object_id: string
  actor_email: string | null
  reason: string | null
  created_at: string
}

export interface ReviewProgress {
  competition_id: string
  total_tasks: number
  submitted: number
  in_progress: number
  assigned: number
  overdue: number
  completion_rate: number
}

// ─────────────── P1/P2 新增接口类型 ───────────────

/** 站内通知（FR-005） */
export interface Notification {
  id: string
  competition_id: string | null
  recipient_id: string | null
  target_role: string | null
  title: string
  body: string
  status: string
  channel: string
  read_by: string | null
  read_at: string | null
  created_at: string
}
export interface UnreadCount {
  count: number
}
export interface NotificationCreate {
  competition_id?: string
  recipient_id?: string
  target_role?: string
  title: string
  body?: string
  channel?: string
}

/** 申诉（FR-020） */
export interface Appeal {
  id: string
  appeal_no: string
  competition_id: string
  team_id: string
  submitted_by: string | null
  reason: string
  status: string
  resolution: string | null
  decision: string | null
  handled_by: string | null
  handled_at: string | null
  created_at: string
  updated_at: string
  /** 后端可能附带展示字段，缺省时前端以「—」兜底 */
  competition_title?: string | null
  team_name?: string | null
  submitted_by_name?: string | null
}

/** 评审异常（FR-017） */
export interface ReviewException {
  id: string
  competition_id: string
  task_id: string
  exception_type: string
  reason: string
  action: string | null
  status: string
  created_by: string | null
  handled_by: string | null
  handled_at: string | null
  handling_note: string | null
  created_at: string
}

/** 处理评审异常的返回（可能新建一条替换任务） */
export interface ResolveOut {
  exception: ReviewException
  new_task: {
    id: string
    competition_id: string
    submission_id: string
    reviewer_id: string
    status: string
    due_at: string | null
    material_ref: string
  } | null
}

/** 评审复核（FR-018） */
export interface Recheck {
  id: string
  competition_id: string
  task_id: string
  original_score_id: string
  frozen_original_json: string
  reason: string
  status: string
  revised_dimension_json: string | null
  revised_total: number | null
  comment: string | null
  reviewer_id: string | null
  decided_by: string | null
  decided_at: string | null
  created_at: string
}

/** 导出任务摘要（FR-025）。列表不回吐完整 content，下载走专用端点。 */
export interface ExportJob {
  id: string
  competition_id: string
  data_kind: string
  export_format: string
  row_count: number
  status: string
  created_at: string
  content?: string
}

/** 归档记录（FR-027） */
export interface ArchiveRecord {
  id: string
  competition_id: string
  snapshot_key: string | null
  archived_by: string | null
  note: string | null
  created_at: string
}

/** 队内协作备注（FR-028） */
export interface CollaborationNote {
  id: string
  team_id: string
  author_id: string | null
  content: string
  created_at: string
  updated_at: string
}

/** 复审问题项（FR-028） */
export interface RevisionIssue {
  id: string
  review_id: string
  description: string
  version_id: string | null
  status: string
  resolution_note: string | null
  handled_by: string | null
  created_at: string
  updated_at: string
}

/** 版本复审（FR-028）。列表不含 issues，详情端点单独返回。 */
export interface RevisionReview {
  id: string
  competition_id: string
  team_id: string
  submission_id: string
  version_id: string
  status: string
  summary: string | null
  raised_by: string | null
  created_at: string
  updated_at: string
}

/** 复审详情 = 复审 + 问题项列表 */
export interface ReviewDetail {
  review: RevisionReview
  issues: RevisionIssue[]
}

/** ── 赛事统计（FR-026）精确类型 ── */
export interface EnrollmentStats {
  total: number
  pending: number
  approved: number
  rejected: number
  needs_info: number
}
export interface SubmissionStats {
  total: number
  draft: number
  submitted: number
  withdrawn: number
  locked: number
}
export interface ReviewStats {
  total_tasks: number
  assigned: number
  in_progress: number
  submitted: number
  overdue: number
  replaced: number
  completion_rate: number
}
export interface ResultStats {
  total: number
  draft: number
  published: number
  avg_final_score: number
  max_final_score: number
  min_final_score: number
  award_distribution: Record<string, number>
}
export interface TeamStats {
  total: number
  with_submission: number
}
export interface CompetitionStatistics {
  competition_id: string
  scope: 'ALL' | 'MY_TEAMS'
  computed_at: string
  enrollment: EnrollmentStats
  submission: SubmissionStats
  review: ReviewStats
  result: ResultStats
  team: TeamStats
  notes: string[]
}
export interface OverviewStatistics {
  users: { total: number; by_role: Record<string, number> }
  competitions: { total: number; by_state: Record<string, number> }
  totals: {
    teams: number
    submissions: number
    review_tasks: number
    published_results: number
  }
}

/** ─────────────── AI 预评级（ADVISORY：仅分流参考，永不进入最终成绩）─────────────── */
export interface RiskFlag {
  code: string
  detail: string
}

export interface AIReviewOut {
  id: string
  version_id: string
  suggested_score: number | null
  confidence: number | null
  evaluation_level: 'L1' | 'L2'
  status: 'PENDING' | 'SUCCEEDED' | 'FAILED' | 'SKIPPED'
  risk_flags: RiskFlag[]
  authority: string
  level_reason: string | null
  error_message: string | null
  rule_version: string | null
  assessed_at: string | null
  created_at: string
}

/** 批量预评级结果摘要 */
export interface AssessSummary {
  total: number
  succeeded: number
  skipped: number
  failed: number
  records: AIReviewOut[]
}

/** 确定性复审触发记录 */
export interface EscalationOut {
  id: string
  competition_id: string
  submission_id: string
  rule_code: string
  rule_version: string
  thresholds: Record<string, number>
  observed: Record<string, unknown>
  action: string
  status: 'OPEN' | 'RESOLVED' | 'DISMISSED'
  note: string | null
  handled_at: string | null
  created_at: string
}

/** JUDGE 视角风险提示：绝不含分数或置信度 */
export interface AIRiskFlagsOut {
  task_id: string
  status: string
  risk_flags: RiskFlag[]
  notice: string
}

const TOKEN_KEY = 'mmcm.token'

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const token = tokenStore.get()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  // FormData 需由浏览器自己带 boundary，不能手写 Content-Type
  if (init.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }

  const resp = await fetch(`/api${path}`, { ...init, headers })

  if (resp.status === 401) {
    tokenStore.clear()
    if (!location.pathname.startsWith('/login')) location.assign('/login')
  }

  if (!resp.ok) {
    let detail = `请求失败（${resp.status}）`
    try {
      const body = await resp.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail)) {
        // Pydantic 校验错误是数组，挑第一条说人话
        detail = body.detail.map((e: { msg: string }) => e.msg).join('；')
      }
    } catch {
      /* 保持默认文案 */
    }
    throw new ApiError(detail, resp.status)
  }

  if (resp.status === 204) return undefined as T
  return (await resp.json()) as T
}

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string; user: User }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  register: (body: {
    email: string
    password: string
    name: string
    school?: string
    role?: 'CAPTAIN' | 'MEMBER'
  }) =>
    request<{ access_token: string; user: User }>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  me: () => request<User>('/auth/me'),

  competitions: () => request<Competition[]>('/competitions'),
  competition: (id: string) => request<Competition>(`/competitions/${id}`),
  lifecycle: () =>
    request<{ states: string[]; transitions: Record<string, string[]> }>('/meta/lifecycle'),

  transition: (id: string, target: string, reason?: string) =>
    request<{ competition: Competition; previous_state: string; allowed_next: string[] }>(
      `/competitions/${id}/transition`,
      { method: 'POST', body: JSON.stringify({ target, reason }) },
    ),

  announcements: (cid: string) =>
    request<{ id: string; title: string; content: string; created_at: string }[]>(
      `/competitions/${cid}/announcements`,
    ),

  myTeams: () => request<Team[]>('/teams'),
  team: (id: string) => request<Team>(`/teams/${id}`),
  createTeam: (competition_id: string, name: string, school?: string) =>
    request<Team>('/teams', { method: 'POST', body: JSON.stringify({ competition_id, name, school }) }),
  addMember: (teamId: string, body: { user_id?: string; email?: string; name?: string; role_in_team?: string }) =>
    request<Team>(`/teams/${teamId}/members`, { method: 'POST', body: JSON.stringify(body) }),

  enrollments: (competitionId?: string) =>
    request<Enrollment[]>(
      `/enrollments${competitionId ? `?competition_id=${competitionId}` : ''}`,
    ),
  enroll: (competition_id: string, team_id: string) =>
    request<Enrollment>('/enrollments', {
      method: 'POST',
      body: JSON.stringify({ competition_id, team_id }),
    }),
  reviewEnrollment: (id: string, status: string, comment?: string) =>
    request<Enrollment>(`/enrollments/${id}/review`, {
      method: 'POST',
      body: JSON.stringify({ status, comment }),
    }),

  submission: (id: string) => request<Submission>(`/submissions/${id}`),
  createSubmission: (enrollmentId: string) =>
    request<Submission>(`/submissions/by-enrollment/${enrollmentId}`, { method: 'POST' }),
  uploadVersion: (submissionId: string, file: File, note?: string) => {
    const fd = new FormData()
    fd.append('file', file)
    if (note) fd.append('note', note)
    return request<SubmissionVersion>(`/submissions/${submissionId}/versions`, {
      method: 'POST',
      body: fd,
    })
  },
  submitSubmission: (id: string) =>
    request<Submission>(`/submissions/${id}/submit`, { method: 'POST' }),

  myTasks: () => request<ReviewTask[]>('/review-tasks/mine'),
  material: (taskId: string) => request<AnonymousMaterial>(`/review-tasks/${taskId}/material`),
  score: (taskId: string, dimension: Record<string, number>, comment: string) =>
    request<{ id: string; total_score: number }>(`/review-tasks/${taskId}/score`, {
      method: 'POST',
      body: JSON.stringify({ dimension, comment }),
    }),

  progress: (cid: string) => request<ReviewProgress>(`/competitions/${cid}/review-progress`),
  results: (cid: string) => request<ResultRow[]>(`/competitions/${cid}/results`),
  allResults: (cid: string) => request<ResultRow[]>(`/competitions/${cid}/results/all`),
  calculate: (cid: string) =>
    request<{ computed: number; skipped: string[]; results: ResultRow[] }>(
      `/competitions/${cid}/results/calculate`,
      { method: 'POST' },
    ),
  publish: (cid: string) =>
    request<ResultRow[]>(`/competitions/${cid}/results/publish`, { method: 'POST' }),

  audit: (limit = 100) => request<AuditRow[]>(`/audit?limit=${limit}`),

  // ── 通知中心（FR-005）──
  myNotifications: (unreadOnly = false) =>
    request<Notification[]>(`/notifications/mine?unread_only=${unreadOnly}`),
  unreadCount: () => request<UnreadCount>('/notifications/mine/unread-count'),
  markNotificationRead: (id: string) =>
    request<Notification>(`/notifications/${id}/read`, { method: 'POST' }),
  sendNotification: (body: NotificationCreate) =>
    request<Notification[]>('/notifications', { method: 'POST', body: JSON.stringify(body) }),
  allNotifications: (params: { competition_id?: string; role?: string } = {}) => {
    const q = new URLSearchParams()
    if (params.competition_id) q.set('competition_id', params.competition_id)
    if (params.role) q.set('role', params.role)
    const s = q.toString()
    return request<Notification[]>(`/notifications${s ? `?${s}` : ''}`)
  },

  // ── 申诉（FR-020）──
  createAppeal: (body: { competition_id: string; team_id: string; reason: string }) =>
    request<Appeal>('/appeals', { method: 'POST', body: JSON.stringify(body) }),
  myAppeals: () => request<Appeal[]>('/appeals/mine'),
  competitionAppeals: (cid: string) => request<Appeal[]>(`/competitions/${cid}/appeals`),
  assignAppeal: (id: string, handlerId: string) =>
    request<Appeal>(`/appeals/${id}/assign`, {
      method: 'POST',
      body: JSON.stringify({ handler_id: handlerId }),
    }),
  decideAppeal: (
    id: string,
    decision: 'ACCEPTED' | 'REJECTED' | 'WITHDRAWN',
    resolution: string,
  ) =>
    request<Appeal>(`/appeals/${id}/decide`, {
      method: 'POST',
      body: JSON.stringify({ decision, resolution }),
    }),

  // ── 评审异常与复核（FR-017 / FR-018）──
  reviewExceptions: (cid: string) =>
    request<ReviewException[]>(`/competitions/${cid}/review-exceptions`),
  createReviewException: (
    taskId: string,
    body: { exception_type: string; reason: string },
  ) =>
    request<ReviewException>(`/review-tasks/${taskId}/exceptions`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  resolveReviewException: (
    id: string,
    body: {
      action: 'REPLACE' | 'EXTEND' | 'MANUAL'
      handling_note: string
      replacement_reviewer_id?: string
      due_at?: string
    },
  ) =>
    request<ResolveOut>(`/review-exceptions/${id}/resolve`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  rechecks: (cid: string) => request<Recheck[]>(`/competitions/${cid}/rechecks`),
  createRecheck: (cid: string, body: { task_id: string; reason: string }) =>
    request<Recheck>(`/competitions/${cid}/rechecks`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  decideRecheck: (
    id: string,
    body: { dimension: Record<string, number>; comment: string },
  ) =>
    request<Recheck>(`/rechecks/${id}/decide`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  // ── 统计（FR-026）──
  competitionStatistics: (cid: string) =>
    request<CompetitionStatistics>(`/competitions/${cid}/statistics`),
  statisticsOverview: () => request<OverviewStatistics>('/statistics/overview'),

  // ── 导出与归档（FR-025 / FR-027）──
  createExport: (cid: string, body: { data_kind: string; export_format: string }) =>
    request<ExportJob>(`/competitions/${cid}/exports`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  exports: (cid: string) => request<ExportJob[]>(`/competitions/${cid}/exports`),

  /**
   * 取导出文件内容供浏览器下载。后端摘要不回吐 content，
   * 统一走 GET /exports/{id}/content（带 token），media_type 由响应头给出。
   */
  exportContent: async (
    job: Pick<ExportJob, 'id' | 'export_format' | 'data_kind'>,
  ): Promise<{ blob: Blob; fileName: string }> => {
    const headers = new Headers()
    const token = tokenStore.get()
    if (token) headers.set('Authorization', `Bearer ${token}`)
    const resp = await fetch(`/api/exports/${job.id}/content`, { headers })
    if (!resp.ok) {
      let detail = `下载失败（${resp.status}）`
      try {
        const body = await resp.json()
        if (typeof body.detail === 'string') detail = body.detail
      } catch {
        /* 保持默认文案 */
      }
      throw new ApiError(detail, resp.status)
    }
    const content = await resp.text()
    const format = job.export_format.toUpperCase()
    const mediaType = format === 'JSON' ? 'application/json' : 'text/csv; charset=utf-8'
    const ext = format === 'JSON' ? 'json' : 'csv'
    return {
      blob: new Blob([content], { type: mediaType }),
      fileName: `${job.data_kind}-${job.id.slice(0, 8)}.${ext}`,
    }
  },

  archiveRecords: (cid: string) => request<ArchiveRecord[]>(`/competitions/${cid}/archive`),
  archiveCompetition: (cid: string, note?: string) =>
    request<ArchiveRecord>(`/competitions/${cid}/archive`, {
      method: 'POST',
      body: JSON.stringify({ note }),
    }),

  // ── 协作与复审（FR-028）──
  createTeamNote: (teamId: string, content: string) =>
    request<CollaborationNote>(`/teams/${teamId}/notes`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    }),
  teamNotes: (teamId: string) => request<CollaborationNote[]>(`/teams/${teamId}/notes`),
  createRevisionReview: (
    cid: string,
    body: { team_id: string; submission_id: string; version_id: string; summary?: string },
  ) =>
    request<RevisionReview>(`/competitions/${cid}/revision-reviews`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  revisionReviews: (cid: string) =>
    request<RevisionReview[]>(`/competitions/${cid}/revision-reviews`),
  revisionReviewDetail: (id: string) => request<ReviewDetail>(`/revision-reviews/${id}`),
  addRevisionIssue: (reviewId: string, body: { description: string; version_id?: string }) =>
    request<RevisionIssue>(`/revision-reviews/${reviewId}/issues`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateRevisionIssue: (
    issueId: string,
    body: { status: string; resolution_note?: string; version_id?: string },
  ) =>
    request<RevisionIssue>(`/revision-issues/${issueId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),

  // ── AI 预评级（ADVISORY，永不进入成绩）──
  /** 端点1：触发该赛事全部已提交作品的预评级 */
  aiAssess: (competitionId: string) =>
    request<AssessSummary>(`/competitions/${competitionId}/ai/assess`, { method: 'POST' }),
  /** 端点2：单个作品评估 */
  aiAssessSubmission: (submissionId: string, versionId?: string) =>
    request<AIReviewOut>(
      `/submissions/${submissionId}/ai-assessment${versionId ? `?version_id=${versionId}` : ''}`,
      { method: 'POST' },
    ),
  /** 端点3：查询赛事的预评级结果 */
  aiAssessments: (competitionId: string, status?: string) =>
    request<AIReviewOut[]>(
      `/competitions/${competitionId}/ai/assessments${status ? `?status=${status}` : ''}`,
    ),
  /** 端点4：JUDGE 视角风险提示（绝不含分数） */
  aiRiskFlags: (taskId: string) =>
    request<AIRiskFlagsOut>(`/review-tasks/${taskId}/ai-risk-flags`),
  /** 端点5：触发确定性复审规则扫描 */
  aiEvaluateEscalations: (competitionId: string) =>
    request<EscalationOut[]>(`/competitions/${competitionId}/ai/escalations/evaluate`, {
      method: 'POST',
    }),
  /** 端点6：查询复审触发队列 */
  aiEscalations: (competitionId: string, status?: string) =>
    request<EscalationOut[]>(
      `/competitions/${competitionId}/ai/escalations${status ? `?status=${status}` : ''}`,
    ),
  /** 端点7：处理复审触发（标记已解决 / 忽略） */
  updateEscalation: (
    id: string,
    body: { status: 'RESOLVED' | 'DISMISSED'; note: string },
  ) =>
    request<EscalationOut>(`/ai/escalations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
}
