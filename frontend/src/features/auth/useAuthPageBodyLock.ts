import { useLayoutEffect } from 'react'

const ROOT_CLS = 'minerva-auth-page'

/**
 * 登录/注册全屏：锁定文档滚动，避免语言/主色切换或打开下拉时整页出现滚动条、宽度抖动。
 */
export function useAuthPageBodyLock() {
  useLayoutEffect(() => {
    const { documentElement, body } = document
    documentElement.classList.add(ROOT_CLS)
    body.classList.add(ROOT_CLS)
    return () => {
      documentElement.classList.remove(ROOT_CLS)
      body.classList.remove(ROOT_CLS)
    }
  }, [])
}
