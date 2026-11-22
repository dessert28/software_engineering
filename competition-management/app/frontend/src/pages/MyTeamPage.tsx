import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Alert, Button, Card, Empty, Form, Input, List, Modal, Select, Space, Tag, Typography } from 'antd'

import { api, type Submission, type Team } from '../api/client'
import { ENROLLMENT_LABEL, SUBMISSION_LABEL, formatBytes, stateLabel } from '../lib/labels'

export default function MyTeamPage() {
  const { message } = App.useApp()
  const qc = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [createForm] = Form.useForm<{ competition_id: string; name: string; school?: string }>()
  const [uploadFor, setUploadFor] = useState<Submission | null>(null)

  const comps = useQuery({ queryKey: ['competitions'], queryFn: api.competitions })
  const teams = useQuery({ queryKey: ['my-teams'], queryFn: api.myTeams })
  const enrollments = useQuery({ queryKey: ['enrollments'], queryFn: () => api.enrollments() })

  const createTeam = useMutation({
    mutationFn: (v: { competition_id: string; name: string; school?: string }) =>
      api.createTeam(v.competition_id, v.name, v.school),
    onSuccess: () => {
      message.success('队伍已创建，你已成为队长')
      setCreateOpen(false)
      createForm.resetFields()
      qc.invalidateQueries({ queryKey: ['my-teams'] })
    },
    onError: (e: Error) => message.error(e.message),
  })

  const enroll = useMutation({
    mutationFn: ({ cid, tid }: { cid: string; tid: string }) => api.enroll(cid, tid),
    onSuccess: () => {
      message.success('报名已提交，等待审核')
      qc.invalidateQueries({ queryKey: ['enrollments'] })
    },
    onError: (e: Error) => message.error(e.message),
  })

  const createSubmission = useMutation({
    mutationFn: (enrollmentId: string) => api.createSubmission(enrollmentId),
    onSuccess: () => {
      message.success('已开启提交')
      qc.invalidateQueries({ queryKey: ['enrollments'] })
    },
    onError: (e: Error) => message.error(e.message),
  })

  const compMap = new Map((comps.data ?? []).map((c) => [c.id, c]))
  const enrollMap = new Map((enrollments.data ?? []).map((e) => [e.team_id, e]))

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Space style={{ width: '100%', justifyContent: 'space-between' }}>
        <div>
          <Typography.Title level={4} style={{ marginBottom: 4 }}>
            我的队伍
          </Typography.Title>
          <Typography.Text type="secondary">
            只有在「报名开放」期内才能建队报名；报名通过审核后才能提交作品。
          </Typography.Text>
        </div>
        <Button type="primary" onClick={() => setCreateOpen(true)}>
          创建队伍
        </Button>
      </Space>

      {teams.data?.length === 0 && <Empty description="你还没有队伍" />}

      {(teams.data ?? []).map((t: Team) => {
        const comp = compMap.get(t.competition_id)
        const enrollment = enrollMap.get(t.id)
        return (
          <Card key={t.id} title={t.name} extra={comp && <Tag>{stateLabel(comp.state)}</Tag>}>
            <Space direction="vertical" size={14} style={{ width: '100%' }}>
              <Typography.Text type="secondary">
                赛事：{comp?.title ?? t.competition_id} · 邀请码：{t.invite_code ?? '—'}
              </Typography.Text>

              <List
                size="small"
                header={<Typography.Text strong>成员</Typography.Text>}
                dataSource={t.members}
                renderItem={(m) => (
                  <List.Item>
                    <Space>
                      <Tag color={m.role_in_team === 'CAPTAIN' ? 'blue' : m.role_in_team === 'ADVISOR' ? 'purple' : 'default'}>
                        {m.role_in_team === 'CAPTAIN' ? '队长' : m.role_in_team === 'ADVISOR' ? '指导' : '队员'}
                      </Tag>
                      {m.name ?? m.user_id} {m.email && <Typography.Text type="secondary">{m.email}</Typography.Text>}
                    </Space>
                  </List.Item>
                )}
              />

              {!enrollment ? (
                <Button
                  type="primary"
                  loading={enroll.isPending}
                  onClick={() => enroll.mutate({ cid: t.competition_id, tid: t.id })}
                >
                  报名参赛
                </Button>
              ) : (
                <Alert
                  type={enrollment.status === 'APPROVED' ? 'success' : enrollment.status === 'REJECTED' ? 'error' : 'info'}
                  showIcon
                  message={`报名状态：${ENROLLMENT_LABEL[enrollment.status] ?? enrollment.status}`}
                  description={enrollment.review_comment ?? undefined}
                  action={
                    enrollment.status === 'APPROVED' ? (
                      <Button size="small" onClick={() => createSubmission.mutate(enrollment.id)}>
                        开启提交
                      </Button>
                    ) : undefined
                  }
                />
              )}
            </Space>
          </Card>
        )
      })}

      <Modal
        title="创建队伍"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => createForm.submit()}
        confirmLoading={createTeam.isPending}
      >
        <Form form={createForm} layout="vertical" onFinish={(v) => createTeam.mutate(v)}>
          <Form.Item name="competition_id" label="赛事" rules={[{ required: true, message: '请选择赛事' }]}>
            <Select
              options={(comps.data ?? [])
                .filter((c) => c.state === 'REGISTRATION_OPEN')
                .map((c) => ({ value: c.id, label: c.title }))}
              placeholder="仅显示报名开放中的赛事"
            />
          </Form.Item>
          <Form.Item name="name" label="队伍名称" rules={[{ required: true, message: '请输入队伍名称' }]}>
            <Input placeholder="同一赛事内不能重名" />
          </Form.Item>
          <Form.Item name="school" label="所属学校">
            <Input placeholder="选填" />
          </Form.Item>
        </Form>
      </Modal>

      <UploadModal submission={uploadFor} onClose={() => setUploadFor(null)} />
    </Space>
  )
}

function UploadModal({ submission, onClose }: { submission: Submission | null; onClose: () => void }) {
  const { message } = App.useApp()
  const qc = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [note, setNote] = useState('')

  const upload = useMutation({
    mutationFn: () => api.uploadVersion(submission!.id, file!, note || undefined),
    onSuccess: (v) => {
      message.success(`已上传 v${v.version_no}`)
      setFile(null)
      setNote('')
      qc.invalidateQueries({ queryKey: ['enrollments'] })
      onClose()
    },
    onError: (e: Error) => message.error(e.message),
  })

  const submit = useMutation({
    mutationFn: () => api.submitSubmission(submission!.id),
    onSuccess: () => {
      message.success('已正式提交')
      qc.invalidateQueries({ queryKey: ['enrollments'] })
      onClose()
    },
    onError: (e: Error) => message.error(e.message),
  })

  if (!submission) return null

  return (
    <Modal
      title="提交作品"
      open
      onCancel={onClose}
      footer={null}
      destroyOnClose
    >
      <Space direction="vertical" size={14} style={{ width: '100%' }}>
        <Space>
          <Tag>{SUBMISSION_LABEL[submission.status] ?? submission.status}</Tag>
          <Typography.Text type="secondary">已上传 {submission.versions.length} 个版本</Typography.Text>
        </Space>

        {submission.versions.length > 0 && (
          <List
            size="small"
            dataSource={submission.versions}
            renderItem={(v) => (
              <List.Item>
                v{v.version_no} · {formatBytes(null)} · {new Date(v.created_at).toLocaleString('zh-CN')}
                {v.note && <Typography.Text type="secondary">（{v.note}）</Typography.Text>}
              </List.Item>
            )}
          />
        )}

        <input
          type="file"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          style={{ display: 'block' }}
        />
        <Input placeholder="版本说明（选填）" value={note} onChange={(e) => setNote(e.target.value)} />
        <Space>
          <Button
            type="primary"
            disabled={!file}
            loading={upload.isPending}
            onClick={() => upload.mutate()}
          >
            上传版本
          </Button>
          <Button
            loading={submit.isPending}
            disabled={submission.versions.length === 0 || submission.status === 'SUBMITTED'}
            onClick={() => submit.mutate()}
          >
            正式提交
          </Button>
        </Space>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          截止时间后无法再上传；提交后再次提交会被拒绝。
        </Typography.Text>
      </Space>
    </Modal>
  )
}
