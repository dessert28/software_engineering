import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App,
  Button,
  Card,
  Empty,
  Input,
  List,
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
  type CollaborationNote,
  type RevisionIssue,
  type RevisionReview,
} from '../api/client'
import {
  ISSUE_STATUS_LABEL,
  REVISION_STATUS_LABEL,
} from '../lib/labels'

const ISSUE_STATUSES = ['OPEN', 'RESOLVED', 'REJECTED']

export default function CollaborationPage() {
  const { message } = App.useApp()
  const qc = useQueryClient()

  const [teamId, setTeamId] = useState<string>()
  const [noteContent, setNoteContent] = useState('')

  const [cid, setCid] = useState<string>()
  const [rvTeamId, setRvTeamId] = useState<string>()
  const [rvSubmissionId, setRvSubmissionId] = useState('')
  const [rvVersionId, setRvVersionId] = useState('')
  const [rvSummary, setRvSummary] = useState('')

  const [issuesReview, setIssuesReview] = useState<RevisionReview | null>(null)
  const [newIssueDesc, setNewIssueDesc] = useState('')
  const [newIssueVersion, setNewIssueVersion] = useState('')
  const [editingIssue, setEditingIssue] = useState<RevisionIssue | null>(null)
  const [editStatus, setEditStatus] = useState('OPEN')
  const [editNote, setEditNote] = useState('')

  const comps = useQuery({ queryKey: ['competitions'], queryFn: api.competitions })
  const teams = useQuery({ queryKey: ['my-teams'], queryFn: api.myTeams })
  const notes = useQuery({
    queryKey: ['team-notes', teamId],
    queryFn: () => api.teamNotes(teamId!),
    enabled: !!teamId,
  })
  const reviews = useQuery({
    queryKey: ['revision-reviews', cid],
    queryFn: () => api.revisionReviews(cid!),
    enabled: !!cid,
  })
  // 复审列表不含问题项，打开弹窗时按 id 拉取详情
  const detail = useQuery({
    queryKey: ['revision-detail', issuesReview?.id],
    queryFn: () => api.revisionReviewDetail(issuesReview!.id),
    enabled: !!issuesReview,
  })
  const issues = detail.data?.issues ?? []

  const createNote = useMutation({
    mutationFn: () => api.createTeamNote(teamId!, noteContent),
    onSuccess: () => {
      message.success('备注已添加')
      setNoteContent('')
      void qc.invalidateQueries({ queryKey: ['team-notes', teamId] })
    },
    onError: (e: Error) => message.error(e.message),
  })

  const createReview = useMutation({
    mutationFn: () =>
      api.createRevisionReview(cid!, {
        team_id: rvTeamId!,
        submission_id: rvSubmissionId.trim(),
        version_id: rvVersionId.trim(),
        summary: rvSummary || undefined,
      }),
    onSuccess: () => {
      message.success('复审已发起')
      setRvSubmissionId('')
      setRvVersionId('')
      setRvSummary('')
      void qc.invalidateQueries({ queryKey: ['revision-reviews', cid] })
    },
    onError: (e: Error) => message.error(e.message),
  })

  const addIssue = useMutation({
    mutationFn: () =>
      api.addRevisionIssue(issuesReview!.id, {
        description: newIssueDesc,
        version_id: newIssueVersion.trim() || undefined,
      }),
    onSuccess: () => {
      message.success('问题项已添加')
      setNewIssueDesc('')
      setNewIssueVersion('')
      void qc.invalidateQueries({ queryKey: ['revision-detail', issuesReview?.id] })
    },
    onError: (e: Error) => message.error(e.message),
  })

  const updateIssue = useMutation({
    mutationFn: () =>
      api.updateRevisionIssue(editingIssue!.id, {
        status: editStatus,
        resolution_note: editNote || undefined,
      }),
    onSuccess: () => {
      message.success('问题项已更新')
      setEditingIssue(null)
      setEditNote('')
      void qc.invalidateQueries({ queryKey: ['revision-detail', issuesReview?.id] })
    },
    onError: (e: Error) => message.error(e.message),
  })

  const reviewColumns: ColumnsType<RevisionReview> = [
    { title: '队伍 ID', dataIndex: 'team_id', width: 150, ellipsis: true },
    { title: '提交 ID', dataIndex: 'submission_id', width: 150, ellipsis: true },
    { title: '版本 ID', dataIndex: 'version_id', width: 150, ellipsis: true },
    { title: '摘要', dataIndex: 'summary', ellipsis: true, render: (v: string | null) => v ?? '—' },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (v: string) => (
        <Tag color={v === 'COMPLETED' ? 'success' : 'processing'}>
          {REVISION_STATUS_LABEL[v] ?? v}
        </Tag>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 90,
      render: (_: unknown, r: RevisionReview) => (
        <Button type="link" size="small" onClick={() => setIssuesReview(r)}>
          问题项
        </Button>
      ),
    },
  ]

  const issueColumns: ColumnsType<RevisionIssue> = [
    { title: '描述', dataIndex: 'description', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (v: string) => (
        <Tag color={v === 'RESOLVED' ? 'success' : v === 'REJECTED' ? 'default' : 'processing'}>
          {ISSUE_STATUS_LABEL[v] ?? v}
        </Tag>
      ),
    },
    {
      title: '处理说明',
      dataIndex: 'resolution_note',
      ellipsis: true,
      render: (v: string | null) => v ?? '—',
    },
    {
      title: '操作',
      key: 'actions',
      width: 80,
      render: (_: unknown, r: RevisionIssue) => (
        <Button
          type="link"
          size="small"
          onClick={() => {
            setEditingIssue(r)
            setEditStatus(r.status)
            setEditNote(r.resolution_note ?? '')
          }}
        >
          更新
        </Button>
      ),
    },
  ]

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Typography.Title level={4} style={{ marginBottom: 4 }}>
          协作与复审
        </Typography.Title>
        <Typography.Text type="secondary">
          记录队内协作备注；发起版本复审、跟踪问题项并更新解决状态。
        </Typography.Text>
      </div>

      <Card title="队内协作备注" size="small">
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Select
            style={{ width: '100%', maxWidth: 460 }}
            placeholder="选择队伍"
            value={teamId}
            onChange={setTeamId}
            options={(teams.data ?? []).map((t) => ({ value: t.id, label: t.name }))}
          />
          {teamId && (
            <>
              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                <Input.TextArea
                  rows={2}
                  value={noteContent}
                  onChange={(e) => setNoteContent(e.target.value)}
                  placeholder="写下协作备注"
                />
                <Button
                  type="primary"
                  loading={createNote.isPending}
                  disabled={!noteContent.trim()}
                  onClick={() => createNote.mutate()}
                >
                  添加备注
                </Button>
              </Space>
              <List
                size="small"
                dataSource={notes.data ?? []}
                locale={{ emptyText: <Empty description="暂无备注" /> }}
                renderItem={(n: CollaborationNote) => (
                  <List.Item>
                    <List.Item.Meta
                      title={n.content}
                      description={`作者 ${n.author_id?.slice(0, 8) ?? '—'} · ${new Date(n.created_at).toLocaleString('zh-CN')}`}
                    />
                  </List.Item>
                )}
              />
            </>
          )}
        </Space>
      </Card>

      <Card title="发起复审" size="small">
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Select
            style={{ width: '100%', maxWidth: 460 }}
            placeholder="选择赛事"
            value={cid}
            onChange={setCid}
            options={(comps.data ?? []).map((c) => ({ value: c.id, label: c.title }))}
          />
          <Space wrap>
            <Select
              style={{ width: 160 }}
              placeholder="队伍"
              value={rvTeamId}
              onChange={setRvTeamId}
              options={(teams.data ?? []).map((t) => ({ value: t.id, label: t.name }))}
            />
            <Input
              style={{ width: 180 }}
              value={rvSubmissionId}
              onChange={(e) => setRvSubmissionId(e.target.value)}
              placeholder="提交 ID"
            />
            <Input
              style={{ width: 180 }}
              value={rvVersionId}
              onChange={(e) => setRvVersionId(e.target.value)}
              placeholder="版本 ID"
            />
          </Space>
          <Input.TextArea
            rows={2}
            value={rvSummary}
            onChange={(e) => setRvSummary(e.target.value)}
            placeholder="复审摘要（可选）"
          />
          <Button
            type="primary"
            loading={createReview.isPending}
            disabled={!cid || !rvTeamId || !rvSubmissionId.trim() || !rvVersionId.trim()}
            onClick={() => createReview.mutate()}
          >
            发起复审
          </Button>
        </Space>
      </Card>

      <Card title="复审列表" size="small">
        <Table
          rowKey="id"
          size="small"
          loading={reviews.isLoading}
          columns={reviewColumns}
          dataSource={reviews.data ?? []}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          locale={{ emptyText: <Empty description={cid ? '暂无复审记录' : '请先选择赛事'} /> }}
        />
      </Card>

      <Modal
        title="复审问题项"
        open={!!issuesReview}
        onCancel={() => setIssuesReview(null)}
        footer={null}
        width={720}
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Space wrap>
            <Input
              style={{ width: 340 }}
              value={newIssueDesc}
              onChange={(e) => setNewIssueDesc(e.target.value)}
              placeholder="问题项描述"
            />
            <Input
              style={{ width: 180 }}
              value={newIssueVersion}
              onChange={(e) => setNewIssueVersion(e.target.value)}
              placeholder="关联版本 ID（可选）"
            />
            <Button
              type="primary"
              loading={addIssue.isPending}
              disabled={newIssueDesc.trim().length < 2}
              onClick={() => addIssue.mutate()}
            >
              添加问题项
            </Button>
          </Space>
          <Table
            rowKey="id"
            size="small"
            loading={detail.isLoading}
            columns={issueColumns}
            dataSource={issues}
            pagination={false}
            locale={{ emptyText: <Empty description="暂无问题项" /> }}
          />
        </Space>
      </Modal>

      <Modal
        title="更新问题项"
        open={!!editingIssue}
        onCancel={() => setEditingIssue(null)}
        onOk={() => updateIssue.mutate()}
        confirmLoading={updateIssue.isPending}
        okText="确认更新"
        cancelText="取消"
        okButtonProps={{
          disabled: editStatus !== 'OPEN' && editNote.trim().length < 2,
        }}
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Typography.Paragraph type="secondary">
            {editingIssue?.description}
          </Typography.Paragraph>
          <Select
            style={{ width: '100%' }}
            value={editStatus}
            onChange={setEditStatus}
            options={ISSUE_STATUSES.map((s) => ({ value: s, label: ISSUE_STATUS_LABEL[s] }))}
          />
          <Input.TextArea
            rows={3}
            value={editNote}
            onChange={(e) => setEditNote(e.target.value)}
            placeholder={
              editStatus !== 'OPEN' ? '处理说明（标记已解决 / 已驳回时必填，至少 2 个字）' : '处理说明（可选）'
            }
          />
        </Space>
      </Modal>
    </Space>
  )
}
