# remove AU roles from all non-whitelist
role = ctx.guild.get_role(AU_CODE_ROLE_ID)
for member in role.members:
    if member.id not in whitelist:
        await move_and_role(member, False)

candidates = sort_queue()
selected = []

for uid in candidates:
    if len(selected) >= amount:
        break
    if can_play(uid):
        selected.append(uid)

# update stats
now = time.time()
for uid in selected:
    last_played[uid] = now
    matches_waited[uid] = 0

for uid in queue:
    if uid not in selected:
        matches_waited[uid] = matches_waited.get(uid, 0) + 1

# assign selected
for uid in selected:
    member = ctx.guild.get_member(uid)
    await move_and_role(member, True)

# rebuild queue
queue = deque(uid for uid in queue if uid not in selected)
queue.extend(selected)

await ctx.send(f"Picked: {', '.join(ctx.guild.get_member(uid).name for uid in selected)}")
