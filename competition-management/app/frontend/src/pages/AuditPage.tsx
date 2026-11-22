import { useQuery } from '@tanstack/react-query'
import { Card, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'

import { api, type AuditRow } from '../api/client'

const ACTION_COLOR: Record<string, string> = {
  CREATE: 'green',
  UPDATE: 'blue',
  DELETE: 'red',
  TRANSITION: 'purple',
  PUBLISH: 'gold',
  LOGIN: 'default',
  SCORE: 'cyan',
}

export default function AuditPage() {
  const { data, isLoading } = useQuery({ queryKey: ['audit'], queryFn: () => api.audit(200) })

  const columns: ColumnsType<AuditRow> = [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 180,
      render: (v: string) => new Date(v).toLocaleString('zh-CN'),
    },
    {
      title: '动作',
      dataIndex: 'action',
      width: 110,
      render: (v: string) => <Tag color={ACTION_COLOR[v] ?? 'default'}>{v}</Tag>,
    },
    { title: '对象类型', dataIndex: 'object_type', width: 160 },
    { title: '对象 ID', dataIndex: 'object_id', width: 220, ellipsis: true },
    { title: '操作人', dataIndex: 'actor_email', width: 200, render: (v: string | null) => v ?? '—' },
    { title: '原因', dataIndex: 'reason', render: (v: string | null) => v ?? '—' },
  ]

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Typography.Title level={4} style={{ marginBottom: 4 }}>
          审计日志
        </Typography.Title>
        <Typography.Text type="secondary">
          只追加不修改；赛事状态迁移、成绩发布、登录等关键动作全部留痕。
        </Typography.Text>
      </div>

      <Card styles={{ body: { padding: 0 } }}>
        <Table
          rowKey="id"
          loading={isLoading}
          columns={columns}
          dataSource={data ?? []}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          size="small"
        />
      </Card>
    </Space>
  )
}
