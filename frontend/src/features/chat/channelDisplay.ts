import type { Channel } from '@/api/types'

const isDm = (channel: Channel) => channel.channel_type === 'direct_message' || channel.channel_type === 'group_dm'

/** A DM's stored `name` isn't a meaningful display value (see ChannelSerializer.participants) —
 * this renders "Jane Doe" (or "Jane Doe, John Smith" for a group DM) from the viewer's own
 * perspective instead. Falls back to the plain channel name for every other channel type. */
export function channelDisplayName(channel: Channel, currentUserId: number | undefined): string {
  if (!isDm(channel)) return channel.name
  const others = channel.participants.filter((p) => p.id !== currentUserId)
  if (others.length === 0) return channel.name
  return others.map((p) => p.display_name).join(', ')
}

export function channelDisplayTitle(channel: Channel, currentUserId: number | undefined): string {
  const name = channelDisplayName(channel, currentUserId)
  return isDm(channel) ? name : `#${name}`
}
