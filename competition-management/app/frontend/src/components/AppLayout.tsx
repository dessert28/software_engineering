import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  AuditOutlined,
  BankOutlined,
  BarChartOutlined,
  BellOutlined,
  ExportOutlined,
  FileDoneOutlined,
  FileSearchOutlined,
  LogoutOutlined,
  RobotOutlined,
  SolutionOutlined,
  TeamOutlined,
  TrophyOutlined,
} from '@ant-design/icons'
import { Avatar, Badge, Layout, Menu, Space, Tag, Typography } from 'antd'

import { api } from '../api/client'
import { useAuth } from './AuthContext'
import { roleLabel } from '../lib/labels'

const { Header, Sider, Content } = Layout

/** 菜单按角色过滤：评审专家看不到报名管理，参赛方看不到审计。 */
export default function AppLayout() {
  const { user, logout, hasRole } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  // 通知未读角标：页面停留期间定时刷新，标记已读后也会由页面 invalidate。
  const unread = useQuery({
    queryKey: ['unread-count'],
    queryFn: api.unreadCount,
    refetchInterval: 30_000,
  })

  const items = useMemo(() => {
    const unreadCount = unread.data?.count ?? 0
    const base = [
      { key: '/competitions', icon: <BankOutlined />, label: <Link to="/competitions">赛事列表</Link> },
    ]
    base.push({
      key: '/notifications',
      icon: <BellOutlined />,
      label: (
        <Badge count={unreadCount} size="small" offset={[12, -2]}>
          <Link to="/notifications">通知</Link>
        </Badge>
      ),
    })
    if (hasRole('CAPTAIN', 'MEMBER', 'TEACHER')) {
      base.push({ key: '/my-team', icon: <TeamOutlined />, label: <Link to="/my-team">我的队伍</Link> })
    }
    if (hasRole('CAPTAIN', 'MEMBER', 'TEACHER', 'ADMIN')) {
      base.push({
        key: '/collaboration',
        icon: <TeamOutlined />,
        label: <Link to="/collaboration">协作复审</Link>,
      })
    }
    if (hasRole('CAPTAIN', 'TEACHER', 'ADMIN')) {
      base.push({ key: '/appeals', icon: <FileSearchOutlined />, label: <Link to="/appeals">申诉管理</Link> })
    }
    if (hasRole('JUDGE', 'ADMIN')) {
      base.push({ key: '/judge', icon: <SolutionOutlined />, label: <Link to="/judge">评审任务</Link> })
      base.push({
        key: '/ai-assessments',
        icon: <RobotOutlined />,
        label: <Link to="/ai-assessments">AI 预评级</Link>,
      })
    }
    if (hasRole('ADMIN')) {
      base.push({
        key: '/review-ops',
        icon: <SolutionOutlined />,
        label: <Link to="/review-ops">评审工作台</Link>,
      })
    }
    base.push({ key: '/results', icon: <TrophyOutlined />, label: <Link to="/results">成绩查询</Link> })
    if (hasRole('ADMIN', 'TEACHER')) {
      base.push({
        key: '/statistics',
        icon: <BarChartOutlined />,
        label: <Link to="/statistics">统计看板</Link>,
      })
    }
    if (hasRole('ADMIN')) {
      base.push({
        key: '/exports',
        icon: <ExportOutlined />,
        label: <Link to="/exports">导出归档</Link>,
      })
      base.push({ key: '/audit', icon: <AuditOutlined />, label: <Link to="/audit">审计日志</Link> })
    }
    return base
  }, [hasRole, unread.data?.count])

  const selected = items.find((i) => location.pathname.startsWith(i.key))?.key ?? '/competitions'

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider theme="light" width={208} style={{ borderRight: '1px solid #f0f0f0' }}>
        <div style={{ padding: '18px 16px 12px' }}>
          <Space align="center">
            <FileDoneOutlined style={{ fontSize: 22, color: '#1677ff' }} />
            <Typography.Text strong>建模竞赛管理</Typography.Text>
          </Space>
        </div>
        <Menu mode="inline" selectedKeys={[selected]} items={items} style={{ borderInlineEnd: 0 }} />
      </Sider>

      <Layout>
        <Header
          style={{
            background: '#fff',
            borderBottom: '1px solid #f0f0f0',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            gap: 16,
            paddingInline: 24,
          }}
        >
          <Space>
            <Avatar size="small" style={{ background: '#1677ff' }}>
              {user?.name?.[0] ?? '?'}
            </Avatar>
            <Typography.Text>{user?.name}</Typography.Text>
            {user && <Tag color="blue">{roleLabel(user.role)}</Tag>}
          </Space>
          <Typography.Link
            onClick={() => {
              logout()
              navigate('/login', { replace: true })
            }}
          >
            <LogoutOutlined /> 退出
          </Typography.Link>
        </Header>

        <Content style={{ padding: 24, background: '#f5f6f8' }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
