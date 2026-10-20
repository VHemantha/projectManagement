import { afterEach, describe, expect, it, vi } from 'vitest'

import { readyForSocket, tokenExpiresSoon } from './client'
import { useAuthStore } from '@/store/authStore'

const b64url = (o: object) => btoa(JSON.stringify(o)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
const token = (expSecondsFromNow: number) =>
  `${b64url({ alg: 'HS256' })}.${b64url({ exp: Math.floor(Date.now() / 1000) + expSecondsFromNow, user_id: 1 })}.sig`

describe('live connections and expired tokens', () => {
  afterEach(() => vi.restoreAllMocks())

  it('reads the expiry from the token', () => {
    expect(tokenExpiresSoon(token(3600))).toBe(false)
    expect(tokenExpiresSoon(token(10))).toBe(true) // within the 30 s margin
    expect(tokenExpiresSoon(token(-7 * 3600))).toBe(true)
    expect(tokenExpiresSoon('not-a-token')).toBe(false) // unreadable: let the server decide
  })

  it('an expired token is refreshed instead of being used for a socket the server would refuse', async () => {
    const fresh = token(3600)
    const post = vi.spyOn((await import('axios')).default, 'post').mockResolvedValue({ data: { access: fresh } })
    useAuthStore.setState({ accessToken: token(-60), refreshToken: 'r' })
    expect(readyForSocket(useAuthStore.getState().accessToken!)).toBe(false)
    expect(readyForSocket(useAuthStore.getState().accessToken!)).toBe(false)
    await vi.waitFor(() => expect(useAuthStore.getState().accessToken).toBe(fresh))
    expect(post).toHaveBeenCalledTimes(1) // one refresh, however many sockets asked
    expect(readyForSocket(fresh)).toBe(true)
  })
})
