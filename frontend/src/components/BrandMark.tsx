import { SHOTLOOM_LOGO_URL } from '../config'

interface BrandMarkProps {
  size?: 'sm' | 'md' | 'lg'
  showText?: boolean
  subtitle?: string
  className?: string
}

const sizeMap = {
  sm: { mark: 'h-8 w-8', title: 'text-sm', subtitle: 'text-[10px]' },
  md: { mark: 'h-11 w-11', title: 'text-xl', subtitle: 'text-xs' },
  lg: { mark: 'h-16 w-16', title: 'text-4xl', subtitle: 'text-sm' },
}

export default function BrandMark({ size = 'md', showText = true, subtitle, className = '' }: BrandMarkProps) {
  const classes = sizeMap[size]

  return (
    <div className={`flex items-center ${size === 'lg' ? 'justify-center gap-4' : 'gap-3'} ${className}`}>
      <img
        src={SHOTLOOM_LOGO_URL}
        alt="ShotLoom"
        className={`${classes.mark} shrink-0 rounded-[30%] shadow-[0_0_24px_rgba(216,162,74,0.24)]`}
      />
      {showText && (
        <div className={size === 'lg' ? 'text-left' : ''}>
          <div className={`${classes.title} font-semibold leading-none tracking-tight text-[#f4efe0]`}>ShotLoom</div>
          {subtitle && <div className={`${classes.subtitle} mt-1 leading-tight text-[#a79d89]`}>{subtitle}</div>}
        </div>
      )}
    </div>
  )
}
