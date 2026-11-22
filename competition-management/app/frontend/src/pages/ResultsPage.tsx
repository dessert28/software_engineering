import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, Empty, Select, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'

import { api, type ResultRow } from '../api/client'
import { useAuth } from '../components/AuthContext'

const AWARD_COLOR: Record<string, string> = {
  一等奖: 'red',
  二等奖: 'orange',
  三等奖: 'blue',
  成功参赛奖: 'default',
}

export default function ResultsPage() {
  const { hasRole } = useAuth()
  const [cid, setCid] = useState<string | undefined>()
  const comps = useQuery({ queryKey: ['competitions'], queryFn: api.competitions })

  const runner = hasRole('ADMIN') && cid ? api.allResults : api.results
  const rows = useQuery({
    queryKey: ['results', cid, hasRole('ADMIN')],
    queryFn: () => runner(cid!),
    enabled: !!cid,
  })

  const columns: ColumnsType<ResultRow> = [
    { title: '名次', dataIndex: 'rank', width: 90, render: (v: number | null) => v ?? '—' },
    { title: '队伍', dataIndex: 'team_name' },
    {
      title: '最终得分',
      dataIndex: 'final_score',
      width: 120,
      render: (v: number | null) => (v == null ? '—' : v.toFixed(2)),
    },
    {
      title: '奖项',
      dataIndex: 'award',
      width: 130,
      render: (v: string | null) => (v ? <Tag color={AWARD_COLOR[v] ?? 'default'}>{v}</Tag> : '—'),
    },
    { title: '参评数', dataIndex: 'review_count', width: 100 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 120,
      render: (v: string) => (
        <Tag color={v === 'PUBLISHED' ? 'success' : 'warning'}>
          {v === 'PUBLISHED' ? '已发布' : '待发布'}
        </Tag>
      ),
    },
  ]

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Typography.Title level={4} style={{ marginBottom: 4 }}>
          成绩查询
        </Typography.Title>
        <Typography.Text type="secondary">
          {hasRole('ADMIN') ? '管理员可见草稿成绩；参赛方只能看到已发布的成绩与自己队伍。' : '结果发布后可见。'}
        </Typography.Text>
      </div>

      <Select
        style={{ maxWidth: 420 }}
        placeholder="选择赛事"
        value={cid}
        onChange={setCid}
        options={(comps.data ?? []).map((c) => ({ value: c.id, label: c.title }))}
      />

      <Card styles={{ body: { padding: 0 } }}>
        <Table
          rowKey="id"
          loading={rows.isLoading}
          columns={columns}
          dataSource={rows.data ?? []}
          pagination={false}
          locale={{ emptyText: <Empty description={cid ? '暂无成绩记录' : '请先选择赛事'} /> }}
        />
      </Card>
    </Space>
  )
}
