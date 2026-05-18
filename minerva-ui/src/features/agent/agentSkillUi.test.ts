import { describe, expect, it } from 'vitest'
import { isAgentMessageUuid, mergeAgentChatWithLocal } from '@/features/agent/agentSkillUi'

describe('isAgentMessageUuid', () => {
  it('accepts canonical UUIDs', () => {
    expect(isAgentMessageUuid('3d50a431-bc2e-4bd3-814b-b56b276fd7fd')).toBe(true)
  })

  it('rejects client-side temp ids', () => {
    expect(isAgentMessageUuid('a-1710000000000')).toBe(false)
  })
})

describe('mergeAgentChatWithLocal', () => {
  it('preserves processLog when ids align', () => {
    const server = [{ id: 'u1', role: 'user' as const, content: 'hi' }]
    const local = [{ id: 'u1', role: 'user' as const, content: 'hi', processLog: ['x'] }]
    expect(mergeAgentChatWithLocal(server, local)[0]?.processLog).toEqual(['x'])
  })
})
