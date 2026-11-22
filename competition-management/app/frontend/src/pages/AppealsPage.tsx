import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App,
  Button,
  Card,
  Empty,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'

import { api, type Appeal } from '../api/client'
import { useAuth } from '../components/AuthContext'
import { APPEAL_DECISION_LABEL, APPEAL_STATUS_LABEL } from '../lib/labels'

const DECISION_COLOR: Record<string, string> = {
  ACCEPTED: 'success',
  REJECTED: 'error',
  WITHDRAWN: 'default',
  CLOSED: 'default',
}

type AppealDecision = 'ACCEPTED' | 'REJECTED' | 'WITHDRAWN'

export default function AppealsPage() {
  const { hasRole } = useAuth()
  const isAdmin = hasRole('ADMIN')
  const { message } = App.useApp()
  const qc = useQueryClient()

  const [submitCid, setSubmitCid] = useState<string>()
  const [submitTeam, setSubmitTeam] = useState<string>()
  const [reason, setReason] = useState('')
  const [adminCid, setAdminCid] = useState<string>()
  const [deciding, setDeciding] = useState<{ id: string; decision: AppealDecision } | null>(null)
  const [resolution, setResolution] = useState('')
  const [assigning, setAssigning] = useState<string | null>(null)
  const [handlerId, setHandlerId] = useState('')

  const comps = useQuery({ queryKey: ['competitions'], queryFn: api.competitions })
  const myTeams = useQuery({
    queryKey: ['my-teams'],
    queryFn: api.myTeams,
    enabled: !isAdmin,
  })
  const mine = useQuery({
    queryKey: ['appeals', 'mine'],
    queryFn: api.myAppeals,
    enabled: !isAdmin,
  })
  const adminRows = useQuery({
    queryKey: ['appeals', 'admin', adminCid],
    queryFn: () => api.competitionAppeals(adminCid!),
    enabled: isAdmin && !!adminCid,
  })

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['appeals'] })
  }

  const submit = useMutation({
    mutationFn: () =>
      api.createAppeal({
        competition_id: submitCid!,
        team_id: submitTeam!,
        reason,
      }),
    onSuccess: () => {
      message.success('申诉已提交')
      setReason('')
      invalidate()
    },
    onError: (e: Error) => message.error(e.message),
  })

  const assign = useMutation({
    mutationFn: () => api.assignAppeal(assigning!, handlerId.trim()),
    onSuccess: () => {
      message.success('已指派处理人')
      setAssigning(null)
      setHandlerId('')
      invalidate()
    },
    onError: (e: Error) => message.error(e.message),
  })

  const decide = useMutation({
    mutationFn: () => api.decideAppeal(deciding!.id, deciding!.decision, resolution),
    onSuccess: () => {
      message.success('申诉已处理')
      setDeciding(null)
      setResolution('')
      invalidate()
    },
    onError: (e: Error) => message.error(e.message),
  })

  const columns: ColumnsType<Appeal> = [
    { title: '申诉编号', dataIndex: 'appeal_no', width: 140 },
    {
      title: '赛事',
      dataIndex: 'competition_id',
      width: 160,
      ellipsis: true,
      render: (v: string, r: Appeal) =>
        r.competition_title ?? comps.data?.find((c) => c.id === v)?.title ?? v.slice(0, 8),
    },
    {
      title: '队伍',
      dataIndex: 'team_id',
      width: 130,
      render: (v: string, r: Appeal) => r.team_name ?? v.slice(0, 8),
    },
    { title: '理由', dataIndex: 'reason', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (v: string) => (
        <Tag color={v === 'OPEN' ? 'processing' : v === 'ASSIGNED' ? 'warning' : 'default'}>
          {APPEAL_STATUS_LABEL[v] ?? v}
        </Tag>
      ),
    },
    {
      title: '处理结果',
      width: 120,
      render: (_: unknown, r: Appeal) =>
        r.decision ? (
          <Tag color={DECISION_COLOR[r.decision] ?? 'default'}>
            {APPEAL_DECISION_LABEL[r.decision] ?? r.decision}
          </Tag>
        ) : (
          '—'
        ),
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 160,
      render: (v: string) => new Date(v).toLocaleString('zh-CN'),
    },
    ...(isAdmin
      ? [
          {
            title: '操作',
            key: 'actions',
            width: 200,
            render: (_: unknown, r: Appeal) =>
              r.status === 'OPEN' || r.status === 'ASSIGNED' ? (
                <Space size={0} wrap>
                  <Button type="link" size="small" onClick={() => setAssigning(r.id)}>
                    指派
                  </Button>
                  {(['ACCEPTED', 'REJECTED', 'WITHDRAWN'] as const).map((d) => (
                    <Button
                      key={d}
                      type="link"
                      size="small"
                      danger={d === 'REJECTED'}
                      onClick={() => {
                        setDeciding({ id: r.id, decision: d })
                        setResolution('')
                      }}
                    >
                      {APPEAL_DECISION_LABEL[d]}
                    </Button>
                  ))}
                </Space>
              ) : (
                '—'
              ),
          },
        ]
      : []),
  ]

  const dataSource = isAdmin ? adminRows.data ?? [] : mine.data ?? []

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Typography.Title level={4} style={{ marginBottom: 4 }}>
          申诉管理
        </Typography.Title>
        <Typography.Text type="secondary">
          {isAdmin
            ? '管理员可按赛事查看申诉，指派处理人并作出通过 / 驳回 / 撤回决定。'
            : '队长 / 指导教师可提交申诉并跟踪处理结果。'}
        </Typography.Text>
      </div>

      {!isAdmin && (
        <Card title="提交申诉" size="small">
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Select
              style={{ width: '100%', maxWidth: 460 }}
              placeholder="选择赛事"
              value={submitCid}
              onChange={setSubmitCid}
              options={(comps.data ?? []).map((c) => ({ value: c.id, label: c.title }))}
            />
            <Select
              style={{ width: '100%', maxWidth: 460 }}
              placeholder="选择队伍（必选）"
              value={submitTeam}
              onChange={setSubmitTeam}
              options={(myTeams.data ?? []).map((t) => ({ value: t.id, label: t.name }))}
            />
            <Input.TextArea
              rows={4}
              maxLength={2000}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="请填写申诉理由（至少 10 个字）"
            />
            <Button
              type="primary"
              loading={submit.isPending}
              disabled={!submitCid || !submitTeam || reason.trim().length < 10}
              onClick={() => submit.mutate()}
            >
              提交申诉
            </Button>
            {!myTeams.data?.length && (
              <Typography.Text type="warning">
                当前账号未加入任何队伍，请先加入队伍后再提交申诉。
              </Typography.Text>
            )}
          </Space>
        </Card>
      )}

      {isAdmin && (
        <Card size="small" title="赛事筛选">
          <Select
            style={{ width: '100%', maxWidth: 460 }}
            placeholder="选择赛事查看申诉"
            value={adminCid}
            onChange={setAdminCid}
            options={(comps.data ?? []).map((c) => ({ value: c.id, label: c.title }))}
          />
        </Card>
      )}

      <Card size="small" title={isAdmin ? '待办申诉' : '我的申诉'}>
        <Table
          rowKey="id"
          size="small"
          loading={isAdmin ? adminRows.isLoading : mine.isLoading}
          columns={columns}
          dataSource={dataSource}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          locale={{
            emptyText: <Empty description={isAdmin && !adminCid ? '请先选择赛事' : '暂无申诉'} />,
          }}
        />
      </Card>

      <Modal
        title="指派处理人"
        open={!!assigning}
        onCancel={() => setAssigning(null)}
        onOk={() => assign.mutate()}
        confirmLoading={assign.isPending}
        okText="确认指派"
        cancelText="取消"
      >
        <Typography.Paragraph type="secondary">
          填写处理人的用户 ID（留空不可提交）。
        </Typography.Paragraph>
        <Input
          value={handlerId}
          onChange={(e) => setHandlerId(e.target.value)}
          placeholder="处理人用户 ID"
        />
      </Modal>

      <Modal
        title={`处理申诉 · ${deciding ? APPEAL_DECISION_LABEL[deciding.decision] : ''}`}
        open={!!deciding}
        onCancel={() => setDeciding(null)}
        onOk={() => decide.mutate()}
        confirmLoading={decide.isPending}
        okText="确认提交"
        cancelText="取消"
        okButtonProps={{ disabled: resolution.trim().length < 5 }}
      >
        <Typography.Paragraph type="secondary">请填写处理意见（至少 5 个字）。</Typography.Paragraph>
        <Input.TextArea
          rows={4}
          value={resolution}
          onChange={(e) => setResolution(e.target.value)}
          placeholder="处理意见（至少 5 个字）"
        />
      </Modal>
    </Space>
  )
}
