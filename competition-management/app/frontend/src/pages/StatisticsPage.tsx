import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Card,
  Col,
  Descriptions,
  Empty,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'

import {
  api,
  type CompetitionStatistics,
  type ResultStats,
} from '../api/client'
import { useAuth } from '../components/AuthContext'
import { ROLE_LABEL, STATE_LABEL } from '../lib/labels'

/** 把「名称 -> 数量」字典转成表格行。 */
function distRows(dist: Record<string, number>, labelOf: (k: string) => string) {
  return Object.entries(dist).map(([key, value]) => ({ key: labelOf(key), value }))
}

export default function StatisticsPage() {
  const { hasRole } = useAuth()
  const isAdmin = hasRole('ADMIN')
  const isTeacher = hasRole('TEACHER')
  const canView = isAdmin || isTeacher
  const [cid, setCid] = useState<string>()

  const comps = useQuery({ queryKey: ['competitions'], queryFn: api.competitions })
  const stats = useQuery({
    queryKey: ['statistics', cid],
    queryFn: () => api.competitionStatistics(cid!),
    enabled: canView && !!cid,
  })
  const overview = useQuery({
    queryKey: ['statistics', 'overview'],
    queryFn: api.statisticsOverview,
    enabled: isAdmin,
  })

  const awardColumns: ColumnsType<{ key: string; value: number }> = [
    { title: '奖项', dataIndex: 'key' },
    { title: '队伍数', dataIndex: 'value' },
  ]

  if (!canView) {
    return (
      <Card>
        <Typography.Text type="secondary">统计看板仅管理员与指导教师可用。</Typography.Text>
      </Card>
    )
  }

  const s = stats.data
  const o = overview.data

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Typography.Title level={4} style={{ marginBottom: 4 }}>
          统计看板
        </Typography.Title>
        <Typography.Text type="secondary">
          按赛事查看报名、提交、评审与成绩等分组统计（FR-026）；管理员额外可看平台总览。
        </Typography.Text>
      </div>

      <Select
        style={{ width: '100%', maxWidth: 460 }}
        placeholder="选择赛事"
        value={cid}
        onChange={setCid}
        options={(comps.data ?? []).map((c) => ({ value: c.id, label: c.title }))}
      />

      {cid && stats.isLoading && <Card loading />}
      {cid && !stats.isLoading && !s && (
        <Card>
          <Empty description="暂无统计数据" />
        </Card>
      )}

      {s && <CompetitionStatsView data={s} awardColumns={awardColumns} />}

      {isAdmin && (
        <Card title="平台总览" size="small">
          {!o ? (
            <Empty description="暂无总览数据" />
          ) : (
            <Space direction="vertical" size={16} style={{ width: '100%' }}>
              <Row gutter={[16, 16]}>
                <Col xs={12} sm={8} md={6}>
                  <Statistic title="平台用户" value={o.users.total} />
                </Col>
                <Col xs={12} sm={8} md={6}>
                  <Statistic title="平台赛事" value={o.competitions.total} />
                </Col>
                <Col xs={12} sm={8} md={6}>
                  <Statistic title="全平台队伍" value={o.totals.teams} />
                </Col>
                <Col xs={12} sm={8} md={6}>
                  <Statistic title="全平台提交" value={o.totals.submissions} />
                </Col>
                <Col xs={12} sm={8} md={6}>
                  <Statistic title="评审任务" value={o.totals.review_tasks} />
                </Col>
                <Col xs={12} sm={8} md={6}>
                  <Statistic title="已发布成绩" value={o.totals.published_results} />
                </Col>
              </Row>
              <Row gutter={[16, 16]}>
                <Col xs={24} md={12}>
                  <Card size="small" title="按角色" type="inner">
                    <Table
                      rowKey="key"
                      size="small"
                      pagination={false}
                      columns={[
                        { title: '角色', dataIndex: 'key' },
                        { title: '人数', dataIndex: 'value' },
                      ]}
                      dataSource={distRows(o.users.by_role, (k) => ROLE_LABEL[k] ?? k)}
                    />
                  </Card>
                </Col>
                <Col xs={24} md={12}>
                  <Card size="small" title="按赛事状态" type="inner">
                    <Table
                      rowKey="key"
                      size="small"
                      pagination={false}
                      columns={[
                        { title: '状态', dataIndex: 'key' },
                        { title: '赛事数', dataIndex: 'value' },
                      ]}
                      dataSource={distRows(o.competitions.by_state, (k) => STATE_LABEL[k] ?? k)}
                    />
                  </Card>
                </Col>
              </Row>
            </Space>
          )}
        </Card>
      )}
    </Space>
  )
}

function CompetitionStatsView({
  data,
  awardColumns,
}: {
  data: CompetitionStatistics
  awardColumns: ColumnsType<{ key: string; value: number }>
}) {
  const r: ResultStats = data.result
  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card size="small" title="赛事统计概览">
        <Space wrap size="large">
          <Tag color="blue">统计范围：{data.scope === 'ALL' ? '全部数据' : '本人指导队伍'}</Tag>
          <Typography.Text type="secondary">
            计算时间：{new Date(data.computed_at).toLocaleString('zh-CN')}
          </Typography.Text>
        </Space>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Card size="small" title="报名">
            <Descriptions size="small" column={1} bordered>
              <Descriptions.Item label="总数">{data.enrollment.total}</Descriptions.Item>
              <Descriptions.Item label="待审核">{data.enrollment.pending}</Descriptions.Item>
              <Descriptions.Item label="已通过">{data.enrollment.approved}</Descriptions.Item>
              <Descriptions.Item label="已驳回">{data.enrollment.rejected}</Descriptions.Item>
              <Descriptions.Item label="需补充信息">{data.enrollment.needs_info}</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card size="small" title="提交">
            <Descriptions size="small" column={1} bordered>
              <Descriptions.Item label="总数">{data.submission.total}</Descriptions.Item>
              <Descriptions.Item label="草稿">{data.submission.draft}</Descriptions.Item>
              <Descriptions.Item label="已提交">{data.submission.submitted}</Descriptions.Item>
              <Descriptions.Item label="已撤回">{data.submission.withdrawn}</Descriptions.Item>
              <Descriptions.Item label="已锁定">{data.submission.locked}</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
      </Row>

      <Card size="small" title="评审">
        <Row gutter={[16, 16]}>
          <Col xs={12} sm={8} md={4}><Statistic title="任务总数" value={data.review.total_tasks} /></Col>
          <Col xs={12} sm={8} md={4}><Statistic title="待评审" value={data.review.assigned} /></Col>
          <Col xs={12} sm={8} md={4}><Statistic title="评审中" value={data.review.in_progress} /></Col>
          <Col xs={12} sm={8} md={4}><Statistic title="已提交" value={data.review.submitted} /></Col>
          <Col xs={12} sm={8} md={4}><Statistic title="已逾期" value={data.review.overdue} /></Col>
          <Col xs={12} sm={8} md={4}><Statistic title="完成率" value={Math.round(data.review.completion_rate * 100)} suffix="%" /></Col>
        </Row>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Card size="small" title="成绩">
            <Row gutter={[16, 16]}>
              <Col xs={12}><Statistic title="记录数" value={r.total} /></Col>
              <Col xs={12}><Statistic title="已发布" value={r.published} /></Col>
              <Col xs={12}><Statistic title="平均分" value={r.avg_final_score} precision={2} /></Col>
              <Col xs={12}><Statistic title="最高分" value={r.max_final_score} precision={2} /></Col>
              <Col xs={12}><Statistic title="最低分" value={r.min_final_score} precision={2} /></Col>
            </Row>
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card size="small" title="奖项分布与队伍">
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Descriptions size="small" column={2} bordered>
                <Descriptions.Item label="队伍总数">{data.team.total}</Descriptions.Item>
                <Descriptions.Item label="已提交队伍">{data.team.with_submission}</Descriptions.Item>
              </Descriptions>
              <Table
                rowKey="key"
                size="small"
                pagination={false}
                columns={awardColumns}
                dataSource={distRows(r.award_distribution, (k) => k)}
                locale={{ emptyText: <Empty description="暂无奖项数据" /> }}
              />
            </Space>
          </Card>
        </Col>
      </Row>

      {data.notes.length > 0 && (
        <Card size="small" title="统计口径说明">
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {data.notes.map((n, i) => (
              <li key={i}>
                <Typography.Text type="secondary">{n}</Typography.Text>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </Space>
  )
}
