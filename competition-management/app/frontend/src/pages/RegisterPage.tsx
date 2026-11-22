import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { LockOutlined, MailOutlined, UserOutlined } from '@ant-design/icons'
import { App, Button, Card, Form, Input, Radio, Space, Typography } from 'antd'

import { api } from '../api/client'
import { useAuth } from '../components/AuthContext'

type RegisterValues = {
  name: string
  email: string
  school?: string
  role: 'CAPTAIN' | 'MEMBER'
  password: string
  confirm: string
}

export default function RegisterPage() {
  const { user, login } = useAuth()
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm<RegisterValues>()

  if (user) return <Navigate to="/competitions" replace />

  async function onFinish(values: RegisterValues) {
    setSubmitting(true)
    try {
      await api.register({
        name: values.name,
        email: values.email,
        school: values.school,
        role: values.role,
        password: values.password,
      })
      const u = await login(values.email, values.password)
      message.success(`注册成功，欢迎 ${u.name}`)
      navigate('/competitions', { replace: true })
    } catch (err) {
      message.error(err instanceof Error ? err.message : '注册失败')
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
        padding: '24px 0',
      }}
    >
      <Card style={{ width: 440, boxShadow: '0 8px 32px rgba(0,0,0,.06)' }}>
        <Space direction="vertical" size={4} style={{ marginBottom: 20 }}>
          <Typography.Title level={3} style={{ marginBottom: 0 }}>
            学生注册
          </Typography.Title>
          <Typography.Text type="secondary">
            注册后即可创建队伍、报名参赛、提交作品
          </Typography.Text>
        </Space>

        <Form
          form={form}
          layout="vertical"
          onFinish={onFinish}
          requiredMark={false}
          initialValues={{ role: 'CAPTAIN' }}
        >
          <Form.Item
            name="name"
            label="姓名"
            rules={[{ required: true, message: '请输入姓名' }, { min: 2, message: '姓名至少 2 个字' }]}
          >
            <Input prefix={<UserOutlined />} placeholder="请输入真实姓名" size="large" />
          </Form.Item>

          <Form.Item
            name="email"
            label="邮箱"
            rules={[
              { required: true, message: '请输入邮箱' },
              { type: 'email', message: '邮箱格式不正确' },
            ]}
          >
            <Input prefix={<MailOutlined />} placeholder="you@example.edu" size="large" />
          </Form.Item>

          <Form.Item name="school" label="学校（选填）">
            <Input placeholder="用于评审同校回避，建议填写" size="large" />
          </Form.Item>

          <Form.Item name="role" label="注册身份" required>
            <Radio.Group
              optionType="button"
              buttonStyle="solid"
              options={[
                { label: '队长（可建队）', value: 'CAPTAIN' },
                { label: '队员（等待邀请）', value: 'MEMBER' },
              ]}
            />
          </Form.Item>

          <Form.Item
            name="password"
            label="密码"
            rules={[
              { required: true, message: '请输入密码' },
              { min: 8, message: '密码至少 8 位' },
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="至少 8 位" size="large" />
          </Form.Item>

          <Form.Item
            name="confirm"
            label="确认密码"
            dependencies={['password']}
            rules={[
              { required: true, message: '请再次输入密码' },
              ({ getFieldValue }) => ({
                validator(_, value: string) {
                  if (!value || getFieldValue('password') === value) return Promise.resolve()
                  return Promise.reject(new Error('两次输入的密码不一致'))
                },
              }),
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="再次输入密码" size="large" />
          </Form.Item>

          <Button type="primary" htmlType="submit" size="large" block loading={submitting}>
            注册并登录
          </Button>
        </Form>

        <div style={{ marginTop: 16, textAlign: 'center' }}>
          <Typography.Text type="secondary">已有账号？</Typography.Text>
          <Link to="/login" style={{ marginLeft: 4 }}>
            返回登录
          </Link>
        </div>

        <Typography.Paragraph type="secondary" style={{ fontSize: 12, margin: '16px 0 0' }}>
          说明：管理员、指导教师、评审专家由平台管理员创建，不开放自助注册。
        </Typography.Paragraph>
      </Card>
    </div>
  )
}
