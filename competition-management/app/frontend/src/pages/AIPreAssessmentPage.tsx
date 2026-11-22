import { useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  App,
  Button,
  Card,
  Descriptions,
  Empty,
  Input,
  Modal,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'

import {
  api,
  type AIReviewOut,
  type AIRiskFlagsOut,
  type AssessSummary,
  type EscalationOut,
  type ReviewTask,
  type RiskFlag,
} from '../api/client'
import { useAuth } from '../components/AuthContext'
import {
  AI_REVIEW_STATUS_LABEL,
  AI_RISK_STATUS_LABEL,
  EVALUATION_LEVEL_LABEL,
  ESCALATION_RULE_CODE_LABEL,
  ESCALATION_STATUS_LABEL,
  RISK_FLAG_CODE_LABEL,
  TASK_LABEL,
} from '../lib/labels'

function formatTime(v: string | null): string {
  return v ? new Date(v).toLocaleString('zh-CN') : '—'
}

function reviewStatusColor(status: AIReviewOut['status']): string {
  switch (status) {
    case 'SUCCEEDED':
      return 'success'
    case 'FAILED':
      return 'error'
    case 'PENDING':
      return 'processing'
    default:
      return 'default'
  }
}

function escalationStatusColor(status: EscalationOut['status']): string {
  switch (status) {
    case 'RESOLVED':
      return 'success'
    case 'OPEN':
      return 'processing'
    default:
      return 'default'
  }
}

/** 风险标记以 Tag 展示，detail 放 Tooltip，避免列过宽。 */
function riskFlagTags(flags: RiskFlag[]): ReactNode {
  if (!flags.length) return '—'
  return (
    <Space size={[0, 4]} wrap>
      {flags.map((f, i) => (
        <Tooltip title={f.detail} key={`${f.code}-${i}`}>
          <Tag color="orange">{RISK_FLAG_CODE_LABEL[f.code] ?? f.code}</Tag>
        </Tooltip>
      ))}
    </Space>
  )
}

export default function AIPreAssessmentPage() {
  const { hasRole } = useAuth()
  const isAdmin = hasRole('ADMIN')
  const isJudge = hasRole('JUDGE')
  const canView = isAdmin || isJudge
  const { message } = App.useApp()
  const qc = useQueryClient()

  const [cid, setCid] = useState<string>()
  const [assessSummary, setAssessSummary] = useState<AssessSummary | null>(null)
  const [escalationResult, setEscalationResult] = useState<string | null>(null)
  const [handling, setHandling] = useState<EscalationOut | null>(null)
  const [handlingStatus, setHandlingStatus] = useState<'RESOLVED' | 'DISMISSED'>('RESOLVED')
  const [handlingNote, setHandlingNote] = useState('')
  const [riskTaskId, setRiskTaskId] = useState<string | null>(null)

  const comps = useQuery({ queryKey: ['competitions'], queryFn: api.competitions })
  const reviews = useQuery({
    queryKey: ['ai-assessments', cid],
    queryFn: () => api.aiAssessments(cid!),
    enabled: isAdmin && !!cid,
  })
  const escalations = useQuery({
    queryKey: ['ai-escalations', cid],
    queryFn: () => api.aiEscalations(cid!),
    enabled: isAdmin && !!cid,
  })
  const myTasks = useQuery({
    queryKey: ['my-review-tasks'],
    queryFn: api.myTasks,
    enabled: isJudge,
  })
  const risk = useQuery({
    queryKey: ['ai-risk-flags', riskTaskId],
    queryFn: () => api.aiRiskFlags(riskTaskId!),
    enabled: isJudge && !!riskTaskId,
  })

  const assess = useMutation({
    mutationFn: () => api.aiAssess(cid!),
    onSuccess: (summary) => {
      setAssessSummary(summary)
      void qc.invalidateQueries({ queryKey: ['ai-assessments'] })
      message.success(`预评级完成：共 ${summary.total} 项，成功 ${summary.succeeded} 项`)
    },
    onError: (e: Error) => message.error(e.message),
  })

  const evaluate = useMutation({
    mutationFn: () => api.aiEvaluateEscalations(cid!),
    onSuccess: (rows) => {
      setEscalationResult(`本次评估触发 ${rows.length} 条复审`)
      void qc.invalidateQueries({ queryKey: ['ai-escalations'] })
      message.success(`复审评估完成，触发 ${rows.length} 条`)
    },
    onError: (e: Error) => message.error(e.message),
  })

  const updateEsc = useMutation({
    mutationFn: () =>
      api.updateEscalation(handling!.id, {
        status: handlingStatus,
        note: handlingNote.trim(),
      }),
    onSuccess: () => {
      message.success('复审触发已处理')
      setHandling(null)
      setHandlingNote('')
      void qc.invalidateQueries({ queryKey: ['ai-escalations'] })
    },
    onError: (e: Error) => message.error(e.message),
  })

  const onCompetitionChange = (value?: string) => {
    setCid(value)
    setAssessSummary(null)
    setEscalationResult(null)
  }

  const openHandling = (row: EscalationOut, status: 'RESOLVED' | 'DISMISSED') => {
    setHandling(row)
    setHandlingStatus(status)
    setHandlingNote('')
  }

  const reviewColumns: ColumnsType<AIReviewOut> = [
    {
      title: '版本 ID',
      dataIndex: 'version_id',
      width: 150,
      ellipsis: true,
      render: (v: string) => v.slice(0, 8),
    },
    {
      title: '评估级别',
      dataIndex: 'evaluation_level',
      width: 120,
      render: (v: AIReviewOut['evaluation_level']) => (
        <Tag color={v === 'L1' ? 'blue' : 'purple'}>{EVALUATION_LEVEL_LABEL[v] ?? v}</Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (v: AIReviewOut['status']) => (
        <Tag color={reviewStatusColor(v)}>{AI_REVIEW_STATUS_LABEL[v] ?? v}</Tag>
      ),
    },
    {
      title: 'AI 参考分',
      dataIndex: 'suggested_score',
      width: 110,
      render: (v: number | null) => (v == null ? '—' : v.toFixed(2)),
    },
    {
      title: '置信度',
      dataIndex: 'confidence',
      width: 100,
      render: (v: number | null) => (v == null ? '—' : `${(v * 100).toFixed(0)}%`),
    },
    {
      title: '风险标记',
      dataIndex: 'risk_flags',
      width: 200,
      render: (flags: RiskFlag[]) => riskFlagTags(flags),
    },
    {
      title: '判定说明',
      dataIndex: 'level_reason',
      ellipsis: true,
      render: (v: string | null) => v ?? '—',
    },
    {
      title: '评估时间',
      dataIndex: 'assessed_at',
      width: 170,
      render: (v: string | null) => formatTime(v),
    },
  ]

  const escalationColumns: ColumnsType<EscalationOut> = [
    {
      title: '规则码',
      dataIndex: 'rule_code',
      width: 120,
      render: (v: string) => ESCALATION_RULE_CODE_LABEL[v] ?? v,
    },
    { title: '作品', dataIndex: 'submission_id', width: 150, ellipsis: true },
    {
      title: '观测依据',
      dataIndex: 'observed',
      width: 240,
      render: (v: Record<string, unknown>) => {
        const text = JSON.stringify(v)
        return (
          <Tooltip title={text}>
            <Typography.Text ellipsis style={{ display: 'block', maxWidth: 220, fontSize: 12 }}>
              {text}
            </Typography.Text>
          </Tooltip>
        )
      },
    },
    { title: '建议动作', dataIndex: 'action', width: 120 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (v: EscalationOut['status']) => (
        <Tag color={escalationStatusColor(v)}>{ESCALATION_STATUS_LABEL[v] ?? v}</Tag>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 150,
      render: (_: unknown, r: EscalationOut) =>
        r.status === 'OPEN' ? (
          <Space size={0}>
            <Button type="link" size="small" onClick={() => openHandling(r, 'RESOLVED')}>
              标记已解决
            </Button>
            <Button type="link" size="small" danger onClick={() => openHandling(r, 'DISMISSED')}>
              忽略
            </Button>
          </Space>
        ) : (
          '—'
        ),
    },
  ]

  const taskColumns: ColumnsType<ReviewTask> = [
    { title: '任务 ID', dataIndex: 'id', width: 150, ellipsis: true },
    { title: '赛事 ID', dataIndex: 'competition_id', width: 150, ellipsis: true },
    {
      title: '任务状态',
      dataIndex: 'status',
      width: 100,
      render: (v: string) => (
        <Tag color={TASK_LABEL[v] ? 'processing' : 'default'}>{TASK_LABEL[v] ?? v}</Tag>
      ),
    },
    {
      title: '截止日期',
      dataIndex: 'due_at',
      width: 170,
      render: (v: string | null) => formatTime(v),
    },
    {
      title: '操作',
      key: 'actions',
      width: 140,
      render: (_: unknown, r: ReviewTask) => (
        <Button type="link" size="small" onClick={() => setRiskTaskId(r.id)}>
          查看 AI 风险提示
        </Button>
      ),
    },
  ]

  if (!canView) {
    return (
      <Card>
        <Typography.Text type="secondary">AI 预评级仅管理员与评审专家可用。</Typography.Text>
      </Card>
    )
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Typography.Title level={4} style={{ marginBottom: 4 }}>
          AI 预评级
        </Typography.Title>
        <Typography.Text type="secondary">
          AI 作为分流路由器：先用规则粗筛（L1），必要时结构化深评（L2），再由确定性规则触发人工复审。
        </Typography.Text>
      </div>

      <Alert
        type="warning"
        showIcon
        message="AI 预评级仅作分流参考"
        description={
          <span>
            所有 AI 结论的 authority=ADVISORY，分数（如有）仅供参考、<strong>永不进入最终成绩</strong>
            ；复审触发由确定性规则产生，而非 AI 直接判定。评审专家端仅展示风险提示、不展示 AI 分数以避免锚定。
          </span>
        }
      />

      {isAdmin && (
        <>
          <Select
            style={{ width: '100%', maxWidth: 460 }}
            placeholder="选择赛事"
            value={cid}
            onChange={onCompetitionChange}
            options={(comps.data ?? []).map((c) => ({ value: c.id, label: c.title }))}
          />

          <Space wrap>
            <Button
              type="primary"
              loading={assess.isPending}
              disabled={!cid}
              onClick={() => {
                setAssessSummary(null)
                assess.mutate()
              }}
            >
              发起 AI 预评级
            </Button>
            <Button
              loading={evaluate.isPending}
              disabled={!cid}
              onClick={() => {
                setEscalationResult(null)
                evaluate.mutate()
              }}
            >
              评估复审触发
            </Button>
          </Space>

          {assessSummary && (
            <Card size="small" title="本次预评级摘要">
              <Space wrap size="large">
                <Statistic title="总数" value={assessSummary.total} />
                <Statistic title="成功" value={assessSummary.succeeded} />
                <Statistic title="跳过" value={assessSummary.skipped} />
                <Statistic title="失败" value={assessSummary.failed} />
              </Space>
            </Card>
          )}
          {escalationResult && <Alert type="info" showIcon message={escalationResult} />}

          <Card title="预评级结果" size="small">
            <Table
              rowKey="id"
              size="small"
              loading={reviews.isLoading}
              columns={reviewColumns}
              dataSource={reviews.data ?? []}
              pagination={{ pageSize: 10, showSizeChanger: false }}
              locale={{ emptyText: <Empty description={cid ? '暂无预评级结果' : '请先选择赛事'} /> }}
            />
          </Card>

          <Card title="复审触发队列" size="small">
            <Table
              rowKey="id"
              size="small"
              loading={escalations.isLoading}
              columns={escalationColumns}
              dataSource={escalations.data ?? []}
              pagination={{ pageSize: 10, showSizeChanger: false }}
              locale={{ emptyText: <Empty description={cid ? '暂无复审触发' : '请先选择赛事'} /> }}
            />
          </Card>
        </>
      )}

      {isJudge && (
        <Card
          title="我的评审任务"
          size="small"
          extra={
            <Typography.Text type="secondary">
              仅显示风险提示，不展示 AI 分数以避免锚定
            </Typography.Text>
          }
        >
          <Table
            rowKey="id"
            size="small"
            loading={myTasks.isLoading}
            columns={taskColumns}
            dataSource={myTasks.data ?? []}
            pagination={{ pageSize: 10, showSizeChanger: false }}
            locale={{ emptyText: <Empty description="暂无评审任务" /> }}
          />
        </Card>
      )}

      {/* 复审触发处理弹窗：处理说明至少 2 个字 */}
      <Modal
        title={handlingStatus === 'RESOLVED' ? '标记复审触发已解决' : '忽略复审触发'}
        open={!!handling}
        onCancel={() => setHandling(null)}
        onOk={() => updateEsc.mutate()}
        confirmLoading={updateEsc.isPending}
        okText="确认提交"
        cancelText="取消"
        okButtonProps={{ disabled: handlingNote.trim().length < 2 }}
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
            规则：{handling ? (ESCALATION_RULE_CODE_LABEL[handling.rule_code] ?? handling.rule_code) : ''}
            {' · '}作品：{handling?.submission_id}
          </Typography.Paragraph>
          <Input.TextArea
            rows={3}
            value={handlingNote}
            onChange={(e) => setHandlingNote(e.target.value)}
            placeholder="请输入处理说明（至少 2 个字）"
          />
        </Space>
      </Modal>

      {/* 评审专家视角：仅风险提示，绝不含分数/置信度 */}
      <Modal
        title="AI 风险提示"
        open={!!riskTaskId}
        onCancel={() => setRiskTaskId(null)}
        footer={<Button onClick={() => setRiskTaskId(null)}>关闭</Button>}
        width={560}
      >
        {risk.isLoading && (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <Spin tip="正在获取风险提示…" />
          </div>
        )}
        {!risk.isLoading && risk.data && (
          <RiskDetails data={risk.data} />
        )}
      </Modal>
    </Space>
  )
}

/** JUDGE 视角详情：只展示 notice 与风险标记清单，不展示任何分数或置信度。 */
function RiskDetails({ data }: { data: AIRiskFlagsOut }) {
  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Alert type="info" showIcon message={data.notice} />
      <Descriptions size="small" column={1} bordered>
        <Descriptions.Item label="任务 ID">{data.task_id}</Descriptions.Item>
        <Descriptions.Item label="任务状态">
          {AI_RISK_STATUS_LABEL[data.status] ?? data.status}
        </Descriptions.Item>
      </Descriptions>
      <Typography.Text strong>风险标记清单</Typography.Text>
      {data.risk_flags.length === 0 ? (
        <Empty description="无风险标记" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <Table
          rowKey={(r, i) => `${r.code}-${i}`}
          size="small"
          pagination={false}
          dataSource={data.risk_flags}
          columns={[
            {
              title: '类型',
              dataIndex: 'code',
              width: 130,
              render: (v: string) => RISK_FLAG_CODE_LABEL[v] ?? v,
            },
            { title: '说明', dataIndex: 'detail' },
          ]}
        />
      )}
      <Typography.Text type="secondary">
        以上仅为风险提示，不展示 AI 分数或置信度，以避免对人工评审产生锚定效应。
      </Typography.Text>
    </Space>
  )
}
