import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App,
  Button,
  Card,
  Empty,
  Form,
  Input,
  Radio,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'

import { api, type Notification } from '../api/client'
import { useAuth } from '../components/AuthContext'
import { NOTIFICATION_STATUS_LABEL, ROLE_LABEL } from '../lib/labels'

const ROLE_OPTIONS = ['ADMIN', 'JUDGE', 'TEACHER', 'CAPTAIN', 'MEMBER'].map((r) => ({
  value: r,
  label: ROLE_LABEL[r] ?? r,
}))

interface SendForm {
  title: string
  body?: string
  competition_id?: string
  targetType: 'role' | 'user'
  target_role?: string
  recipient_id?: string
}

export default function NotificationsPage() {
  const { hasRole } = useAuth()
  const isAdmin = hasRole('ADMIN')
  const { message } = App.useApp()
  const qc = useQueryClient()
  const [form] = Form.useForm<SendForm>()
  const [scope, setScope] = useState<'mine' | 'all'>('mine')
  const [unreadOnly, setUnreadOnly] = useState(false)

  const comps = useQuery({ queryKey: ['competitions'], queryFn: api.competitions })
  const mine = useQuery({
    queryKey: ['notifications', 'mine', unreadOnly],
    queryFn: () => api.myNotifications(unreadOnly),
    enabled: scope === 'mine',
  })
  const all = useQuery({
    queryKey: ['notifications', 'all'],
    queryFn: () => api.allNotifications(),
    enabled: isAdmin && scope === 'all',
  })

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['notifications'] })
    void qc.invalidateQueries({ queryKey: ['unread-count'] })
  }

  const markRead = useMutation({
    mutationFn: (id: string) => api.markNotificationRead(id),
    onSuccess: () => {
      message.success('已标记为已读')
      invalidate()
    },
    onError: (e: Error) => message.error(e.message),
  })

  const send = useMutation({
    mutationFn: (v: SendForm) =>
      api.sendNotification({
        title: v.title,
        body: v.body,
        competition_id: v.competition_id,
        target_role: v.targetType === 'role' ? v.target_role : undefined,
        recipient_id: v.targetType === 'user' ? v.recipient_id : undefined,
      }),
    onSuccess: (rows) => {
      message.success(`已发送 ${rows.length} 条通知`)
      form.resetFields()
      invalidate()
    },
    onError: (e: Error) => message.error(e.message),
  })

  const rows = scope === 'mine' ? mine.data ?? [] : all.data ?? []
  const compTitle = (id: string | null) =>
    id ? comps.data?.find((c) => c.id === id)?.title ?? id.slice(0, 8) : '全站'

  const columns: ColumnsType<Notification> = [
    { title: '标题', dataIndex: 'title', width: 180, ellipsis: true },
    { title: '正文', dataIndex: 'body', ellipsis: true },
    {
      title: '赛事',
      dataIndex: 'competition_id',
      width: 160,
      ellipsis: true,
      render: (v: string | null) => compTitle(v),
    },
    {
      title: '接收对象',
      width: 130,
      render: (_: unknown, r: Notification) =>
        r.recipient_id ? `用户 ${r.recipient_id.slice(0, 8)}…` : ROLE_LABEL[r.target_role ?? ''] ?? r.target_role ?? '—',
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (v: string) => (
        <Tag color={v === 'READ' ? 'success' : v === 'FAILED' ? 'error' : 'processing'}>
          {NOTIFICATION_STATUS_LABEL[v] ?? v}
        </Tag>
      ),
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 160,
      render: (v: string) => new Date(v).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      render: (_: unknown, r: Notification) =>
        r.status === 'READ' ? (
          <Typography.Text type="secondary">—</Typography.Text>
        ) : (
          <Button
            type="link"
            size="small"
            loading={markRead.isPending}
            onClick={() => markRead.mutate(r.id)}
          >
            标记已读
          </Button>
        ),
    },
  ]

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Typography.Title level={4} style={{ marginBottom: 4 }}>
          通知中心
        </Typography.Title>
        <Typography.Text type="secondary">
          站内通知支持按角色广播或指定用户；未读通知会在左侧菜单显示角标。
        </Typography.Text>
      </div>

      {isAdmin && (
        <Card title="发送通知" size="small">
          <Form<SendForm>
            form={form}
            layout="vertical"
            initialValues={{ targetType: 'role' }}
            onFinish={(v) => send.mutate(v)}
          >
            <Form.Item
              name="title"
              label="标题"
              rules={[{ required: true, message: '请输入标题' }]}
            >
              <Input maxLength={200} placeholder="通知标题" />
            </Form.Item>
            <Form.Item name="body" label="正文">
              <Input.TextArea rows={3} placeholder="通知正文（可选）" />
            </Form.Item>
            <Form.Item name="competition_id" label="关联赛事（可选）">
              <Select
                allowClear
                placeholder="全站通知"
                options={(comps.data ?? []).map((c) => ({ value: c.id, label: c.title }))}
              />
            </Form.Item>
            <Form.Item name="targetType" label="接收方式">
              <Radio.Group>
                <Radio value="role">按角色广播</Radio>
                <Radio value="user">指定用户</Radio>
              </Radio.Group>
            </Form.Item>
            <Form.Item
              noStyle
              shouldUpdate={(prev, cur) => prev.targetType !== cur.targetType}
            >
              {({ getFieldValue }) =>
                getFieldValue('targetType') === 'role' ? (
                  <Form.Item
                    name="target_role"
                    label="目标角色"
                    rules={[{ required: true, message: '请选择目标角色' }]}
                  >
                    <Select placeholder="选择角色" options={ROLE_OPTIONS} />
                  </Form.Item>
                ) : (
                  <Form.Item
                    name="recipient_id"
                    label="目标用户 ID"
                    rules={[{ required: true, message: '请输入用户 ID' }]}
                  >
                    <Input placeholder="填写接收用户的 ID" />
                  </Form.Item>
                )
              }
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" loading={send.isPending}>
                发送通知
              </Button>
            </Form.Item>
          </Form>
        </Card>
      )}

      <Card
        size="small"
        title={isAdmin ? '通知列表' : '我的通知'}
        extra={
          <Space>
            <Radio.Group
              size="small"
              value={unreadOnly}
              onChange={(e) => setUnreadOnly(e.target.value)}
            >
              <Radio.Button value={false}>全部</Radio.Button>
              <Radio.Button value={true}>仅未读</Radio.Button>
            </Radio.Group>
            {isAdmin && (
              <Radio.Group size="small" value={scope} onChange={(e) => setScope(e.target.value)}>
                <Radio.Button value="mine">我的</Radio.Button>
                <Radio.Button value="all">全部（管理）</Radio.Button>
              </Radio.Group>
            )}
          </Space>
        }
      >
        <Table
          rowKey="id"
          size="small"
          loading={scope === 'mine' ? mine.isLoading : all.isLoading}
          columns={columns}
          dataSource={rows}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          locale={{ emptyText: <Empty description="暂无通知" /> }}
        />
      </Card>
    </Space>
  )
}
