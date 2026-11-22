import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App,
  Button,
  Card,
  Empty,
  Input,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'

import { api, type ArchiveRecord, type ExportJob } from '../api/client'
import { useAuth } from '../components/AuthContext'
import { EXPORT_FORMAT_LABEL, EXPORT_STATUS_LABEL } from '../lib/labels'

const DATA_KINDS = [
  { value: 'ENROLLMENTS', label: '报名数据' },
  { value: 'TEAMS', label: '队伍信息' },
  { value: 'SUBMISSIONS', label: '提交作品' },
  { value: 'REVIEWS', label: '评审数据' },
  { value: 'RESULTS', label: '成绩结果' },
  { value: 'AUDIT', label: '审计日志' },
]
const FORMATS = ['CSV', 'JSON']

export default function ExportsPage() {
  const { hasRole } = useAuth()
  const isAdmin = hasRole('ADMIN')
  const { message, modal } = App.useApp()
  const qc = useQueryClient()

  const [cid, setCid] = useState<string>()
  const [dataKind, setDataKind] = useState('SUBMISSIONS')
  const [format, setFormat] = useState('CSV')
  const [archiveNote, setArchiveNote] = useState('')

  const comps = useQuery({ queryKey: ['competitions'], queryFn: api.competitions })
  const exports = useQuery({
    queryKey: ['exports', cid],
    queryFn: () => api.exports(cid!),
    enabled: isAdmin && !!cid,
  })
  const archives = useQuery({
    queryKey: ['archives', cid],
    queryFn: () => api.archiveRecords(cid!),
    enabled: isAdmin && !!cid,
  })

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['exports'] })
    void qc.invalidateQueries({ queryKey: ['archives'] })
    void qc.invalidateQueries({ queryKey: ['competitions'] })
  }

  const createExport = useMutation({
    mutationFn: () =>
      api.createExport(cid!, { data_kind: dataKind, export_format: format }),
    onSuccess: () => {
      message.success('导出任务已创建')
      invalidate()
    },
    onError: (e: Error) => message.error(e.message),
  })

  const archive = useMutation({
    mutationFn: (note: string) => api.archiveCompetition(cid!, note || undefined),
    onSuccess: () => {
      message.success('赛事已归档')
      setArchiveNote('')
      invalidate()
    },
    onError: (e: Error) => message.error(e.message),
  })

  const download = async (job: ExportJob) => {
    try {
      const { blob, fileName } = await api.exportContent(job)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = fileName
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const exportColumns: ColumnsType<ExportJob> = [
    {
      title: '数据类型',
      dataIndex: 'data_kind',
      width: 130,
      render: (v: string) => DATA_KINDS.find((d) => d.value === v)?.label ?? v,
    },
    {
      title: '格式',
      dataIndex: 'export_format',
      width: 90,
      render: (v: string) => EXPORT_FORMAT_LABEL[v] ?? v,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (v: string) => (
        <Tag color={v === 'COMPLETED' ? 'success' : v === 'FAILED' ? 'error' : 'processing'}>
          {EXPORT_STATUS_LABEL[v] ?? v}
        </Tag>
      ),
    },
    { title: '行数', dataIndex: 'row_count', width: 90 },
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 160,
      render: (v: string) => new Date(v).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 90,
      render: (_: unknown, r: ExportJob) =>
        r.status === 'COMPLETED' ? (
          <Button type="link" size="small" onClick={() => void download(r)}>
            下载
          </Button>
        ) : (
          '—'
        ),
    },
  ]

  const archiveColumns: ColumnsType<ArchiveRecord> = [
    { title: '记录 ID', dataIndex: 'id', width: 150, ellipsis: true },
    {
      title: '快照',
      dataIndex: 'snapshot_key',
      ellipsis: true,
      render: (v: string | null) => v ?? '—',
    },
    {
      title: '备注',
      dataIndex: 'note',
      ellipsis: true,
      render: (v: string | null) => v ?? '—',
    },
    {
      title: '归档时间',
      dataIndex: 'created_at',
      width: 160,
      render: (v: string) => new Date(v).toLocaleString('zh-CN'),
    },
  ]

  if (!isAdmin) {
    return (
      <Card>
        <Typography.Text type="secondary">导出与归档仅管理员可用。</Typography.Text>
      </Card>
    )
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Typography.Title level={4} style={{ marginBottom: 4 }}>
          导出与归档
        </Typography.Title>
        <Typography.Text type="secondary">
          按赛事导出数据并下载，查看归档记录；归档通过赛事状态迁移到 ARCHIVED 完成。
        </Typography.Text>
      </div>

      <Select
        style={{ width: '100%', maxWidth: 460 }}
        placeholder="选择赛事"
        value={cid}
        onChange={setCid}
        options={(comps.data ?? []).map((c) => ({ value: c.id, label: c.title }))}
      />

      <Card title="发起导出" size="small">
        <Space wrap>
          <Select
            style={{ width: 160 }}
            value={dataKind}
            onChange={setDataKind}
            options={DATA_KINDS}
          />
          <Select
            style={{ width: 120 }}
            value={format}
            onChange={setFormat}
            options={FORMATS.map((f) => ({ value: f, label: EXPORT_FORMAT_LABEL[f] ?? f }))}
          />
          <Button
            type="primary"
            loading={createExport.isPending}
            disabled={!cid}
            onClick={() => createExport.mutate()}
          >
            发起导出
          </Button>
        </Space>
      </Card>

      <Card title="导出历史" size="small">
        <Table
          rowKey="id"
          size="small"
          loading={exports.isLoading}
          columns={exportColumns}
          dataSource={exports.data ?? []}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          locale={{ emptyText: <Empty description={cid ? '暂无导出记录' : '请先选择赛事'} /> }}
        />
      </Card>

      <Card
        title="归档记录"
        size="small"
        extra={
          <Space>
            <Input
              style={{ width: 200 }}
              value={archiveNote}
              onChange={(e) => setArchiveNote(e.target.value)}
              placeholder="归档说明（可选）"
            />
            <Button
              danger
              loading={archive.isPending}
              disabled={!cid}
              onClick={() =>
                modal.confirm({
                  title: '归档该赛事？',
                  content: '归档后赛事进入终态，操作会写入审计日志。',
                  onOk: () => archive.mutateAsync(archiveNote),
                })
              }
            >
              归档赛事
            </Button>
          </Space>
        }
      >
        <Table
          rowKey="id"
          size="small"
          loading={archives.isLoading}
          columns={archiveColumns}
          dataSource={archives.data ?? []}
          pagination={{ pageSize: 10, showSizeChanger: false }}
          locale={{ emptyText: <Empty description={cid ? '暂无归档记录' : '请先选择赛事'} /> }}
        />
      </Card>
    </Space>
  )
}
