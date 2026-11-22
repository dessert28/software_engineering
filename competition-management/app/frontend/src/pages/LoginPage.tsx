import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { LockOutlined, MailOutlined } from '@ant-design/icons'
import { App, Button, Card, Form, Input, Space, Typography } from 'antd'

import { useAuth } from '../components/AuthContext'

const DEMO_ACCOUNTS = [
  { email: 'admin@example.edu', label: '管理员' },
  { email: 'teacher@example.edu', label: '指导教师' },
  { email: 'judge@example.edu', label: '评审专家' },
]

export default function LoginPage() {
  const { user, login } = useAuth()
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm<{ email: string; password: string }>()

  if (user) return <Navigate to="/competitions" replace />

  async function onFinish(values: { email: string; password: string }) {
    setSubmitting(true)
    try {
      const u = await login(values.email, values.password)
      message.success(`欢迎回来，${u.name}`)
      navigate('/competitions', { replace: true })
    } catch (err) {
      message.error(err instanceof Error ? err.message : '登录失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        background: 'linear-gradient(135deg,#eef3ff 0%,#f7f8fa 100%)',
      }}
    >
      <Card style={{ width: 400, boxShadow: '0 8px 32px rgba(0,0,0,.06)' }}>
        <Space direction="vertical" size={4} style={{ marginBottom: 24 }}>
          <Typography.Title level={3} style={{ marginBottom: 0 }}>
            数学建模比赛管理系统
          </Typography.Title>
          <Typography.Text type="secondary">浙江树人学院 · 软件工程课程项目</Typography.Text>
        </Space>

        <Form form={form} layout="vertical" onFinish={onFinish} requiredMark={false}>
          <Form.Item
            name="email"
            label="邮箱"
            rules={[{ required: true, message: '请输入邮箱' }]}
          >
            <Input prefix={<MailOutlined />} placeholder="admin@example.edu" size="large" />
          </Form.Item>
          <Form.Item
            name="password"
            label="密码"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="Passw0rd!" size="large" />
          </Form.Item>
          <Button type="primary" htmlType="submit" size="large" block loading={submitting}>
            登录
          </Button>
        </Form>

        <div style={{ marginTop: 20 }}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            演示账号（密码均为 Passw0rd!）
          </Typography.Text>
          <Space wrap style={{ marginTop: 8 }}>
            {DEMO_ACCOUNTS.map((a) => (
              <Button
                key={a.email}
                size="small"
                onClick={() => form.setFieldsValue({ email: a.email, password: 'Passw0rd!' })}
              >
                {a.label}
              </Button>
            ))}
          </Space>
        </div>
      </Card>
    </div>
  )
}
