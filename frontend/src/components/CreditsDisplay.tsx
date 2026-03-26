import { useEffect, useState } from 'react'
import axios from 'axios'
import { useAuth } from '../contexts/AuthContext'

export default function CreditsDisplay() {
  const { user } = useAuth()
  const [balance, setBalance] = useState<number | null>(null)

  useEffect(() => {
    if (!user) return
    axios.get('/api/credits/me')
      .then(res => setBalance(res.data.balance))
      .catch(() => {})
  }, [user])

  if (balance === null) return null

  return (
    <div className="flex items-center gap-1.5 text-xs">
      <span className="text-yellow-400">⚡</span>
      <span className="text-gray-300">{balance} 积分</span>
    </div>
  )
}
