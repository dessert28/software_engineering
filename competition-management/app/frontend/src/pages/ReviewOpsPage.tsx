import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App,
  Button,
  Card,
  Empty,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'

import {
  api,
  type Recheck,
  type ReviewException,
} from '../api/client'
import { useAuth } from '../components/AuthContext'
import {
  EXCEPTION_ACTION_LABEL,
  RECHECK_STATUS_LABEL,
  REVIEW_EXCEPTION_STATUS_LABEL,
  REVIEW_EXCEPTION_TYPE_LABEL,
} from '../lib/labels'

const EXCEPTION_TYPES = ['OVERDUE', 'REFUSAL', 'CONFLICT', 'OTHER']
const ACTIONS = ['REPLACE', 'EXTEND', 'MANUAL']

export default function ReviewOpsPage() {
  const { hasRole } = useAuth()
  const isAdmin = hasRole('ADMIN')
  const { message } = App.useApp()
  const qc = useQueryClient()

  const [cid, setCid] = useState<string>()

  const [excTaskId, setExcTaskId] = useState('')
  const [excType, setExcType] = useState('OVERDUE')
  const [excReason, setExcReason] = useState('')
  const [resolving, setResolving] = useState<ReviewException | null>(null)
  const [resolveAction, setResolveAction] = useState<'REPLACE' | 'EXTEND' | 'MANUAL'>('MANUAL')
  const [resolveNote, setResolveNote] = useState('')
  const [replacementReviewerId, setReplacementReviewerId] = useState('')
  const [dueAt, setDueAt] = useState('')

  const [rkTaskId, setRkTaskId] = useState('')
  const [rkReason, setRkReason] = useState('')
  const [deciding, setDeciding] = useState<Recheck | null>(null)
  // 复核决定需提交三个维度分（modeling/solving/writing），总分由后端按 weight 计算
  const [dimModeling, setDimModeling] = useState<number | null>(null)
  const [dimSolving, setDimSolving] = useState<number | null>(null)
  const [dimWriting, setDimWriting] = useState<number | null>(null)
  const [recheckComment, setRecheckComment] = useState('')

  const comps = useQuery({ queryKey: ['competitions'], queryFn: api.competitions })
  const exceptions = useQuery({
    queryKey: ['review-exceptions', cid],
    queryFn: () => api.reviewExceptions(cid!),
    enabled: isAdmin && !!cid,
  })
  const rechecks = useQuery({
    queryKey: ['rechecks', cid],
    queryFn: () => api.rechecks(cid!),
    enabled: isAdmin && !!cid,
  })

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['review-exceptions'] })
    void qc.invalidateQueries({ queryKey: ['rechecks'] })
  }

  const createException = useMutation({
    mutationFn: () =>
      api.createReviewException(excTaskId.trim(), {
        exception_type: excType,
        reason: excReason,
      }),
    onSuccess: () => {
      message.success('评审异常已登记')
      setExcTaskId('')
      setExcReason('')
      invalidate()
    },
    onError: (e: Error) => message.error(e.message),
  })

  const resolve = useMutation({
    mutationFn: () =>
      api.resolveReviewException(resolving!.id, {
        action: resolveAction,
        handling_note: resolveNote,
        replacement_reviewer_id:
          resolveAction === 'REPLACE' ? replacementReviewerId.trim() || undefined : undefined,
        due_at: resolveAction === 'EXTEND' && dueAt ? new Date(dueAt).toISOString() : undefined,
      }),
    onSuccess: () => {
      message.success('异常已处理')
      setResolving(null)
      setResolveNote('')
      setReplacementReviewerId('')
      setDueAt('')
      invalidate()
    },
    onError: (e: Error) => message.error(e.message),
  })

  const createRecheck = useMutation({
    mutationFn: () =>
      api.createRecheck(cid!, { task_id: rkTaskId.trim(), reason: rkReason }),
    onSuccess: () => {
      message.success('复核已发起')
      setRkTaskId('')
      setRkReason('')
      invalidate()
    },
    onError: (e: Error) => message.error(e.message),
  })

  const decide = useMutation({
    mutationFn: () =>
      api.decideRecheck(deciding!.id, {
        dimension: {
          modeling: dimModeling ?? 0,
          solving: dimSolving ?? 0,
          writing: dimWriting ?? 0,
        },
        comment: recheckComment,
      }),
    onSuccess: () => {
      message.success('复核决定已提交')
      setDeciding(null)
      setDimModeling(null)
      setDimSolving(null)
      setDimWriting(null)
      setRecheckComment('')
      invalidate()
    },
    onError: (e: Error) => message.error(e.message),
  })

  const decideReady =
    dimModeling != null && dimSolving != null && dimWriting != null && recheckComment.trim().length >= 10
  const resolveReady =
    resolveNote.trim().length > 0 &&
    (resolveAction !== 'REPLACE' || !!replacementReviewerId.trim()) &&
    (resolveAction !== 'EXTEND' || !!dueAt)

  const exceptionColumns: ColumnsType<ReviewException> = [
    { title: '任务 ID', dataIndex: 'task_id', width: 150, ellipsis: true },
    {
      title: '异常类型',
      dataIndex: 'exception_type',
      width: 110,
      render: (v: string) => REVIEW_EXCEPTION_TYPE_LABEL[v] ?? v,
    },
    { title: '原因', dataIndex: 'reason', ellipsis: true },
    {
      title: '处理方式',
      dataIndex: 'action',
      width: 110,
      render: (v: string | null) => (v ? EXCEPTION_ACTION_LABEL[v] ?? v : '—'),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (v: string) => (
        <Tag color={v === 'RESOLVED' ? 'success' : 'processing'}>
          {REVIEW_EXCEPTION_STATUS_LABEL[v] ?? v}
        </Tag>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 80,
      render: (_: unknown, r: ReviewException) =>
        r.status === 'OPEN' ? (
          <Button
            type="link"
            size="small"
            onClick={() => {
              setResolving(r)
              setResolveAction('MANUAL')
              setResolveNote('')
              setReplacementReviewerId('')
              setDueAt('')
            }}
          >
            处理
          </Button>
        ) : (
          '—'
        ),
    },
  ]

  const recheckColumns: ColumnsType<Recheck> = [
    { title: '任务 ID', dataIndex: 'task_id', width: 150, ellipsis: true },
    { title: '原因', dataIndex: 'reason', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (v: string) => (
        <Tag color={v === 'COMPLETED' ? 'success' : 'processing'}>
          {RECHECK_STATUS_LABEL[v] ?? v}
        </Tag>
      ),
    },
    {
      title: '复核得分',
      dataIndex: 'revised_total',
      width: 100,
      render: (v: number | null) => (v == null ? '—' : v.toFixed(2)),
    },
    {
      title: '操作',
      key: 'actions',
      width: 80,
      render: (_: unknown, r: Recheck) =>
        r.status !== 'COMPLETED' ? (
          <Button
            type="link"
            size="small"
            onClick={() => {
              setDeciding(r)
              setDimModeling(null)
              setDimSolving(null)
              setDimWriting(null)
              setRecheckComment('')
            }}
          >
            复核决定
          </Button>
        ) : (
          '—'
        ),
    },
  ]

  if (!isAdmin) {
    return (
      <Card>
        <Typography.Text type="secondary">评审工作台仅管理员可用。</Typography.Text>
      </Card>
    )
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Typography.Title level={4} style={{ marginBottom: 4 }}>
          评审工作台
        </Typography.Title>
        <Typography.Text type="secondary">
          登记并处理评审异常（替换 / 延时 / 人工），发起评分复核并提交复核决定。
        </Typography.Text>
      </div>

      <Select
        style={{ width: '100%', maxWidth: 460 }}
        placeholder="选择赛事"
        value={cid}
        onChange={setCid}
        options={(comps.data ?? []).map((c) => ({ value: c.id, label: c.title }))}
      />

      <Card title="评审异常" size="small">
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Space wrap>
            <Input
              style={{ width: 180 }}
              value={excTaskId}
              onChange={(e) => setExcTaskId(e.target.value)}
              placeholder="评审任务 ID"
            />
            <Select
              style={{ width: 140 }}
              value={excType}
              onChange={setExcType}
              options={EXCEPTION_TYPES.map((t) => ({
                value: t,
                label: REVIEW_EXCEPTION_TYPE_LABEL[t],
              }))}
            />
            <Input
              style={{ width: 220 }}
              value={excReason}
              onChange={(e) => setExcReason(e.target.value)}
              placeholder="异常原因"
            />
            <Button
              type="primary"
              loading={createException.isPending}
              disabled={!excTaskId.trim() || !excReason.trim()}
              onClick={() => createException.mutate()}
            >
              登记异常
            </Button>
          </Space>
          <Table
            rowKey="id"
            size="small"
            loading={exceptions.isLoading}
            columns={exceptionColumns}
            dataSource={exceptions.data ?? []}
            pagination={{ pageSize: 10, showSizeChanger: false }}
            locale={{ emptyText: <Empty description={cid ? '暂无评审异常' : '请先选择赛事'} /> }}
          />
        </Space>
      </Card>

      <Card title="评审复核" size="small">
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Space wrap>
            <Input
              style={{ width: 180 }}
              value={rkTaskId}
              onChange={(e) => setRkTaskId(e.target.value)}
              placeholder="评审任务 ID"
            />
            <Input
              style={{ width: 260 }}
              value={rkReason}
              onChange={(e) => setRkReason(e.target.value)}
              placeholder="复核原因"
            />
            <Button
              type="primary"
              loading={createRecheck.isPending}
              disabled={!cid || !rkTaskId.trim() || !rkReason.trim()}
              onClick={() => createRecheck.mutate()}
            >
              发起复核
            </Button>
          </Space>
          <Table
            rowKey="id"
            size="small"
            loading={rechecks.isLoading}
            columns={recheckColumns}
            dataSource={rechecks.data ?? []}
            pagination={{ pageSize: 10, showSizeChanger: false }}
            locale={{ emptyText: <Empty description={cid ? '暂无复核记录' : '请先选择赛事'} /> }}
          />
        </Space>
      </Card>

      <Modal
        title="处理评审异常"
        open={!!resolving}
        onCancel={() => setResolving(null)}
        onOk={() => resolve.mutate()}
        confirmLoading={resolve.isPending}
        okText="确认处理"
        cancelText="取消"
        okButtonProps={{ disabled: !resolveReady }}
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Typography.Paragraph type="secondary">
            异常原因：{resolving?.reason}
          </Typography.Paragraph>
          <Select
            style={{ width: '100%' }}
            value={resolveAction}
            onChange={setResolveAction}
            options={ACTIONS.map((a) => ({ value: a, label: EXCEPTION_ACTION_LABEL[a] }))}
          />
          {resolveAction === 'REPLACE' && (
            <Input
              value={replacementReviewerId}
              onChange={(e) => setReplacementReviewerId(e.target.value)}
              placeholder="替换专家用户 ID（必填）"
            />
          )}
          {resolveAction === 'EXTEND' && (
            <Input
              type="datetime-local"
              value={dueAt}
              onChange={(e) => setDueAt(e.target.value)}
              placeholder="新的截止时间（必填）"
            />
          )}
          <Input.TextArea
            rows={3}
            value={resolveNote}
            onChange={(e) => setResolveNote(e.target.value)}
            placeholder="处理说明（必填）"
          />
        </Space>
      </Modal>

      <Modal
        title="提交复核决定"
        open={!!deciding}
        onCancel={() => setDeciding(null)}
        onOk={() => decide.mutate()}
        confirmLoading={decide.isPending}
        okText="确认提交"
        cancelText="取消"
        okButtonProps={{ disabled: !decideReady }}
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Typography.Paragraph type="secondary">
            复核原因：{deciding?.reason}
          </Typography.Paragraph>
          <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
            请重新给出各维度分（0–100），最终得分将由后端按评分权重计算。
          </Typography.Paragraph>
          <Space wrap>
            <Space direction="vertical" size={4}>
              <Typography.Text type="secondary">模型建立</Typography.Text>
              <InputNumber min={0} max={100} precision={1} value={dimModeling} onChange={setDimModeling} placeholder="建模" />
            </Space>
            <Space direction="vertical" size={4}>
              <Typography.Text type="secondary">求解与验证</Typography.Text>
              <InputNumber min={0} max={100} precision={1} value={dimSolving} onChange={setDimSolving} placeholder="求解" />
            </Space>
            <Space direction="vertical" size={4}>
              <Typography.Text type="secondary">论文表达</Typography.Text>
              <InputNumber min={0} max={100} precision={1} value={dimWriting} onChange={setDimWriting} placeholder="论文" />
            </Space>
          </Space>
          <Input.TextArea
            rows={3}
            value={recheckComment}
            onChange={(e) => setRecheckComment(e.target.value)}
            placeholder="复核意见（至少 10 个字）"
          />
        </Space>
      </Modal>
    </Space>
  )
}
