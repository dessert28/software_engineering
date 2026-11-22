import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App,
  Button,
  Card,
  Descriptions,
  Empty,
  Input,
  List,
  Space,
  Statistic,
  Steps,
  Tag,
  Typography,
} from 'antd'

import { api, type Enrollment } from '../api/client'
import { useAuth } from '../components/AuthContext'
import { ENROLLMENT_LABEL, stateColor, stateLabel } from '../lib/labels'

const MAIN_LINE = [
  'DRAFT',
  'REGISTRATION_OPEN',
  'REGISTRATION_CLOSED',
  'QUALIFICATION_REVIEW',
  'RUNNING',
  'SUBMISSION_OPEN',
  'SUBMISSION_CLOSED',
  'REVIEWING',
  'RESULT_PENDING',
  'RESULT_PUBLISHED',
  'APPEAL',
  'ARCHIVED',
]

export default function CompetitionDetailPage() {
  const { id = '' } = useParams()
  const { hasRole } = useAuth()
  const { message, modal } = App.useApp()
  const qc = useQueryClient()
  const [reason, setReason] = useState('')

  const comp = useQuery({ queryKey: ['competition', id], queryFn: () => api.competition(id) })
  const meta = useQuery({ queryKey: ['lifecycle'], queryFn: api.lifecycle })
  const progress = useQuery({
    queryKey: ['progress', id],
    queryFn: () => api.progress(id),
    enabled: hasRole('ADMIN'),
  })
  const enrollments = useQuery({
    queryKey: ['enrollments', id],
    queryFn: () => api.enrollments(id),
    enabled: hasRole('ADMIN'),
  })

  const transition = useMutation({
    mutationFn: ({ target, why }: { target: string; why?: string }) =>
      api.transition(id, target, why),
    onSuccess: (r) => {
      message.success(`已迁移到「${stateLabel(r.competition.state)}」`)
      setReason('')
      qc.invalidateQueries({ queryKey: ['competition', id] })
      qc.invalidateQueries({ queryKey: ['competitions'] })
      qc.invalidateQueries({ queryKey: ['audit'] })
    },
    onError: (e: Error) => message.error(e.message),
  })

  const reviewEnrollment = useMutation({
    mutationFn: ({ eid, status }: { eid: string; status: string }) =>
      api.reviewEnrollment(eid, status),
    onSuccess: () => {
      message.success('已更新报名审核状态')
      qc.invalidateQueries({ queryKey: ['enrollments', id] })
    },
    onError: (e: Error) => message.error(e.message),
  })

  const calculate = useMutation({
    mutationFn: () => api.calculate(id),
    onSuccess: (r) =>
      message.success(`已汇总 ${r.computed} 支队伍${r.skipped.length ? `，跳过 ${r.skipped.length} 项` : ''}`),
    onError: (e: Error) => message.error(e.message),
  })

  const publish = useMutation({
    mutationFn: () => api.publish(id),
    onSuccess: (rows) => message.success(`已发布 ${rows.length} 条成绩`),
    onError: (e: Error) => message.error(e.message),
  })

  if (comp.isLoading || !comp.data) return <Card loading />

  const c = comp.data
  const allowed = meta.data?.transitions[c.state] ?? []
  const stepIndex = MAIN_LINE.indexOf(c.state)

  function confirmForce(target: string) {
    if (allowed.includes('ARCHIVED') && target === 'ARCHIVED' && !reason.trim()) {
      message.warning('强制归档必须填写原因')
      return
    }
    modal.confirm({
      title: `确认迁移到「${stateLabel(target)}」？`,
      content: reason ? `原因：${reason}` : '该操作会写入审计日志。',
      onOk: () => transition.mutateAsync({ target, why: reason || undefined }),
    })
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card>
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Space align="center" wrap>
            <Typography.Title level={4} style={{ margin: 0 }}>
              {c.title}
            </Typography.Title>
            <Tag color={stateColor(c.state)}>{stateLabel(c.state)}</Tag>
          </Space>

          <Steps
            size="small"
            current={stepIndex < 0 ? 0 : stepIndex}
            items={MAIN_LINE.slice(0, 8).map((s) => ({ title: stateLabel(s) }))}
            style={{ marginTop: 8 }}
          />

          <Descriptions size="small" column={{ xs: 1, sm: 2, md: 3 }}>
            <Descriptions.Item label="届次">{c.edition ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="主办方">{c.organizer ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="队伍规模">
              {c.min_team_size}–{c.max_team_size} 人
            </Descriptions.Item>
            <Descriptions.Item label="报名窗口">
              {c.registration_opens_at
                ? `${new Date(c.registration_opens_at).toLocaleDateString('zh-CN')} 起`
                : '未设置'}
            </Descriptions.Item>
            <Descriptions.Item label="提交截止">
              {c.submission_closes_at
                ? new Date(c.submission_closes_at).toLocaleString('zh-CN')
                : '未设置'}
            </Descriptions.Item>
            <Descriptions.Item label="允许的下一步">
              {allowed.length ? allowed.map((s) => stateLabel(s)).join(' / ') : '无（终态）'}
            </Descriptions.Item>
          </Descriptions>

          {hasRole('ADMIN') && allowed.length > 0 && (
            <Card size="small" title="状态迁移" type="inner">
              <Space direction="vertical" size={10} style={{ width: '100%' }}>
                <Input.TextArea
                  rows={2}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="迁移原因（强制归档时必填，其他情况可选）"
                />
                <Space wrap>
                  {allowed.map((s) => (
                    <Button
                      key={s}
                      type={s === 'ARCHIVED' ? 'default' : 'primary'}
                      danger={s === 'ARCHIVED'}
                      loading={transition.isPending}
                      onClick={() => confirmForce(s)}
                    >
                      迁到「{stateLabel(s)}」
                    </Button>
                  ))}
                </Space>
              </Space>
            </Card>
          )}
        </Space>
      </Card>

      {hasRole('ADMIN') && (
        <>
          <Card title="评审与成绩" size="small">
            <Space size="large" wrap direction="vertical" style={{ width: '100%' }}>
              <Space size="large" wrap>
                <Statistic title="评审任务" value={progress.data?.total_tasks ?? 0} />
                <Statistic title="已完成" value={progress.data?.submitted ?? 0} />
                <Statistic title="待评审" value={progress.data?.assigned ?? 0} />
                <Statistic title="已逾期" value={progress.data?.overdue ?? 0} />
                <Statistic
                  title="完成率"
                  value={Math.round((progress.data?.completion_rate ?? 0) * 100)}
                  suffix="%"
                />
              </Space>
              <Space wrap>
                <Button loading={calculate.isPending} onClick={() => calculate.mutate()}>
                  汇总成绩
                </Button>
                <Button
                  type="primary"
                  loading={publish.isPending}
                  onClick={() =>
                    modal.confirm({
                      title: '发布成绩？',
                      content: '发布后参赛方即可查询，且不能撤销。',
                      onOk: () => publish.mutateAsync(),
                    })
                  }
                >
                  发布成绩
                </Button>
              </Space>
            </Space>
          </Card>

          <Card title="报名审核" size="small">
            <List
              dataSource={enrollments.data ?? []}
              locale={{ emptyText: <Empty description="暂无报名记录" /> }}
              renderItem={(e: Enrollment) => (
                <List.Item
                  actions={
                    e.status === 'PENDING'
                      ? [
                          <Button
                            key="ok"
                            type="link"
                            size="small"
                            onClick={() => reviewEnrollment.mutate({ eid: e.id, status: 'APPROVED' })}
                          >
                            通过
                          </Button>,
                          <Button
                            key="no"
                            type="link"
                            size="small"
                            danger
                            onClick={() => reviewEnrollment.mutate({ eid: e.id, status: 'REJECTED' })}
                          >
                            驳回
                          </Button>,
                        ]
                      : []
                  }
                >
                  <List.Item.Meta
                    title={`队伍 ${e.team_id.slice(0, 8)}…`}
                    description={
                      <Space>
                        <Tag color={e.status === 'APPROVED' ? 'success' : e.status === 'REJECTED' ? 'error' : 'warning'}>
                          {ENROLLMENT_LABEL[e.status] ?? e.status}
                        </Tag>
                        {e.review_comment && <span>{e.review_comment}</span>}
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          </Card>
        </>
      )}
    </Space>
  )
}
