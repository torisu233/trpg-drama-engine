// 访问密码状态（取代 window.prompt——部分手机浏览器会封锁 prompt 导致无法输入）。
// 单一真相来源：所有 API 请求的 X-App-Password 都读 auth.pw；App 以 auth.ok 决定是否放行。
import { reactive } from 'vue'

export const auth = reactive({
  pw: localStorage.getItem('app_pw') || '',  // 已存密码（与旧版同键，向后兼容）
  ok: false,                                 // 是否已通过验证（决定放行 router-view）
})

export function setPw(pw) {
  auth.pw = pw
  localStorage.setItem('app_pw', pw)
}

// 401 或注销时清掉，并让全站退回登录闸
export function clearPw() {
  auth.pw = ''
  auth.ok = false
  localStorage.removeItem('app_pw')
}
