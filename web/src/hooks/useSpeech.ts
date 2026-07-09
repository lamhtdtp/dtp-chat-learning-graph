import { useEffect, useRef, useState } from 'react'

// Nhận diện giọng nói qua Web Speech API (Chrome Android, Safari iOS, Chrome desktop).
// Cần HTTPS (hoặc localhost) và quyền micro. Ngôn ngữ: tiếng Việt.
function getSR(): any {
  if (typeof window === 'undefined') return null
  return (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition || null
}

export function useSpeech(onText: (text: string) => void) {
  const supported = !!getSR()
  const [listening, setListening] = useState(false)
  const recRef = useRef<any>(null)
  const baseRef = useRef('')
  const cbRef = useRef(onText)
  cbRef.current = onText

  useEffect(() => () => recRef.current?.abort?.(), [])

  const stop = () => recRef.current?.stop?.()

  const start = (base: string) => {
    const Ctor = getSR()
    if (!Ctor) return
    const rec = new Ctor()
    rec.lang = 'vi-VN'
    rec.interimResults = true
    rec.continuous = false
    baseRef.current = base ? base.trimEnd() + ' ' : ''
    rec.onresult = (e: any) => {
      let txt = ''
      for (let i = 0; i < e.results.length; i++) txt += e.results[i][0].transcript
      cbRef.current(baseRef.current + txt)
    }
    rec.onend = () => {
      setListening(false)
      recRef.current = null
    }
    rec.onerror = () => {
      setListening(false)
      recRef.current = null
    }
    recRef.current = rec
    rec.start()
    setListening(true)
  }

  const toggle = (base: string) => (listening ? stop() : start(base))

  return { supported, listening, toggle }
}
