import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App,
  Button,
  Card,
  Descriptions,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Modal,
  Progress,
  Space,
  Tag,
  Typography,
} from 'antd'

import { api, type ReviewTask } from '../api/client'
import { TASK_LABEL, formatBytes } from '../lib/labels'

export default function JudgeTasksPage() {
  const [active, setActive] = useState<ReviewTask | null>(null)
  const tasks = useQuery({ queryKey: ['my-tasks'], queryFn: api.myTasks })

  const pending = (tasks.data ?? []).filter((t) => t.status !== 'SUBMITTED')
  const done = (tasks.data ?? []).filter((t) => t.status === 'SUBMITTED')
  const rate = tasks.data?.length ? Math.round((done.length / tasks.data.length) * 100) : 0

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Typography.Title level={4} style={{ marginBottom: 4 }}>
          评审任务
        </Typography.Title>
        <Typography.Text type="secondary">
          材料按匿名字段下发，页面不显示队伍名称与学校。
        </Typography.Text>
      </div>

      <Card size="small">
        <Space size="large" align="center">
          <Progress type="circle" size={72} percent={rate} />
          <Space direction="vertical" size={2}>
            <Typography.Text>共 {tasks.data?.length ?? 0} 项</Typography.Text>
            <Typography.Text type="secondary">待评审 {pending.length} 项</Typography.Text>
          </Space>
        </Space>
      </Card>

      <Card title="待评审" size="small">
        <List
          dataSource={pending}
          locale={{ emptyText: <Empty description="没有待评审任务" /> }}
          renderItem={(t) => (
            <List.Item
              actions={[
                <Button key="go" type="link" onClick={() => setActive(t)}>
                  评阅
                </Button>,
              ]}
            >
              <List.Item.Meta
                title={<Space><Tag color="blue">{t.material_ref}</Tag></Space>}
                description={
                  <Space>
                    <Tag color={t.status === 'OVERDUE' ? 'red' : 'default'}>
                      {TASK_LABEL[t.status] ?? t.status}
                    </Tag>
                    {t.due_at && <span>截止 {new Date(t.due_at).toLocaleDateString('zh-CN')}</span>}
                  </Space>
                }
              />
            </List.Item>
          )}
        />
      </Card>

      <Card title="已完成" size="small">
        <List
          dataSource={done}
          locale={{ emptyText: <Empty description="暂无已评分任务" /> }}
          renderItem={(t) => (
            <List.Item>
              <Space>
                <Tag color="green">{t.material_ref}</Tag>
                <Typography.Text type="secondary">已评分</Typography.Text>
              </Space>
            </List.Item>
          )}
        />
      </Card>

      <ScoreModal task={active} onClose={() => setActive(null)} />
    </Space>
  )
}

function ScoreModal({ task, onClose }: { task: ReviewTask | null; onClose: () => void }) {
  const { message } = App.useApp()
  const qc = useQueryClient()
  const [form] = Form.useForm<Record<string, number>>()
  const [comment, setComment] = useState('')

  const material = useQuery({
    queryKey: ['material', task?.id],
    queryFn: () => api.material(task!.id),
    enabled: !!task,
  })

  const submit = useMutation({
    mutationFn: (dimension: Record<string, number>) => api.score(task!.id, dimension, comment),
    onSuccess: (r) => {
      message.success(`评分已提交，加权总分 ${r.total_score}`)
      qc.invalidateQueries({ queryKey: ['my-tasks'] })
      onClose()
    },
    onError: (e: Error) => message.error(e.message),
  })

  if (!task) return null

  const rubric = material.data?.rubric ?? []

  return (
    <Modal
      title="评阅材料"
      open
      onCancel={onClose}
      footer={null}
      width={680}
      destroyOnClose
    >
      {material.isLoading && <Card loading />}
      {material.data && (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Descriptions size="small" column={2} bordered>
            <Descriptions.Item label="作品编号">{material.data.problem_code}</Descriptions.Item>
            <Descriptions.Item label="版本">v{material.data.version_no}</Descriptions.Item>
            <Descriptions.Item label="文件">{material.data.file_name ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="大小">{formatBytes(material.data.file_size)}</Descriptions.Item>
          </Descriptions>

          <Form form={form} layout="vertical" onFinish={(v) => submit.mutate(v)}>
            {rubric.map((r) => (
              <Form.Item
                key={r.key}
                name={r.key}
                label={`${r.label}（权重 ${r.weight}%）`}
                rules={[{ required: true, message: `请给出${r.label}分数` }]}
              >
                <InputNumber min={0} max={100} style={{ width: '100%' }} placeholder="0–100" />
              </Form.Item>
            ))}

            <Form.Item label="评语" required extra="不少于 10 字，评审意见会留档">
              <Input.TextArea
                rows={3}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="请说明模型假设、求解过程与论文表述的具体问题"
              />
            </Form.Item>

            <Space>
              <Button type="primary" htmlType="submit" loading={submit.isPending}>
                提交评分
              </Button>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                提交后不可修改
              </Typography.Text>
            </Space>
          </Form>
        </Space>
      )}
    </Modal>
  )
}
