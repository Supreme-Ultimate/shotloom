import { useParams, useNavigate } from 'react-router-dom'
import AnalysisPage from './AnalysisPage'

export default function AnalysisPageWrapper() {
  const { videoId } = useParams<{ videoId: string }>()
  const navigate = useNavigate()

  if (!videoId || isNaN(Number(videoId))) {
    navigate('/')
    return null
  }

  return <AnalysisPage videoId={Number(videoId)} onBack={() => navigate('/')} />
}
