import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Card, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'

import { api, type Competition } from '../api/client'
import { useAuth } from '../components/AuthContext'
import { stateColor, stateLabel } from '../lib/labels'

export default function CompetitionListPage() {
  const { hasRole } = useAuth()
  const { data, isLoading } = useQuery({ queryKey: ['competitions'], queryFn: api.competitions })

  const columns: ColumnsType<Competition> = [
    {
      title: '赛事名称',
      dataIndex: 'title',
      render: (title: string, row) => <Link to={`/competitions/${row.id}`}>{title}</Link>,
    },
    { title: '届次', dataIndex: 'edition', width: 120, render: (v: string | null) => v ?? '—' },
    {
      title: '状态',
      dataIndex: 'state',
      width: 130,
      filters: [...new Set((data ?? []).map((c) => c.state))].map((s) => ({
        text: stateLabel(s),
        value: s,
      })),
      onFilter: (value, row) => row.state === value,
      render: (s: string) => <Tag color={stateColor(s)}>{stateLabel(s)}</Tag>,
    },
    {
      title: '队伍规模',
      width: 120,
      render: (_, row) => `${row.min_team_size}–${row.max_team_size} 人`,
    },
    {
      title: '提交截止',
      dataIndex: 'submission_closes_at',
      width: 180,
      render: (v: string | null) => (v ? new Date(v).toLocaleString('zh-CN') : '未设置'),
    },
  ]

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Typography.Title level={4} style={{ marginBottom: 4 }}>
          赛事列表
        </Typography.Title>
        <Typography.Text type="secondary">
          {hasRole('ADMIN')
            ? '点击赛事进入详情，可在详情页执行状态迁移、分配评审与发布成绩。'
            : '点击赛事查看详情与公告；报名请在「我的队伍」中操作。'}
        </Typography.Text>
      </div>

      <Card styles={{ body: { padding: 0 } }}>
        <Table
          rowKey="id"
          loading={isLoading}
          columns={columns}
          dataSource={data ?? []}
          pagination={false}
          locale={{ emptyText: '暂无赛事' }}
        />
      </Card>
    </Space>
  )
}
