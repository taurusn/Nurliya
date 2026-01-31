'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import { LogEntry } from './api'

type WSMessage = {
  type: 'analysis' | 'stats' | 'job_update' | 'logs'
  data: any
}

type UseWebSocketReturn = {
  isConnected: boolean
  lastMessage: WSMessage | null
  stats: any | null
  recentAnalysis: any | null
  recentLogs: LogEntry[]
}

export function useWebSocket(): UseWebSocketReturn {
  const [isConnected, setIsConnected] = useState(false)
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null)
  const [stats, setStats] = useState<any>(null)
  const [recentAnalysis, setRecentAnalysis] = useState<any>(null)
  const [recentLogs, setRecentLogs] = useState<LogEntry[]>([])
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>()

  const connect = useCallback(() => {
    const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws'

    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        setIsConnected(true)
      }

      ws.onclose = () => {
        setIsConnected(false)
        // Reconnect after 3 seconds
        reconnectTimeoutRef.current = setTimeout(connect, 3000)
      }

      ws.onerror = () => {
        ws.close()
      }

      ws.onmessage = (event) => {
        try {
          const message: WSMessage = JSON.parse(event.data)
          setLastMessage(message)

          if (message.type === 'stats') {
            setStats(message.data)
          } else if (message.type === 'analysis') {
            setRecentAnalysis(message.data)
          } else if (message.type === 'logs') {
            setRecentLogs(message.data)
          }
        } catch (e) {
          console.error('Failed to parse message:', e)
        }
      }
    } catch (e) {
      console.error('WebSocket connection failed:', e)
      reconnectTimeoutRef.current = setTimeout(connect, 3000)
    }
  }, [])

  useEffect(() => {
    connect()

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [connect])

  return { isConnected, lastMessage, stats, recentAnalysis, recentLogs }
}
