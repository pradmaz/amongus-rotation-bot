@bot.tree.command(name="pick", description="High-speed fair player selection")
async def pick(interaction: discord.Interaction, amount: int):

    await interaction.response.defer()

    guild = interaction.guild
    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)

    code_role = guild.get_role(CODE_ROLE_ID)
    whitelist = guild.get_role(WHITELIST_ROLE_ID)
    blacklist = guild.get_role(BLACKLIST_ROLE_ID)

    # ========= CLEAN OLD MATCH =========

    cleanup_tasks = []

    for uid in list(current_match):

        member = guild.get_member(uid)

        if not member or whitelist in member.roles:
            continue

        async def cleanup(m=member):

            try:

                if code_role in m.roles:
                    await m.remove_roles(code_role)

                if (
                    m.voice
                    and m.voice.channel
                    and m.voice.channel.id == CLOSED_VC_ID
                ):
                    await m.move_to(public_vc)

            except:
                pass

        cleanup_tasks.append(cleanup())

    if cleanup_tasks:
        await asyncio.gather(*cleanup_tasks)

    current_match.clear()

    # ========= BUILD LIST =========

    eligible = []
    whitelist_to_move = []

    for m in public_vc.members:

        if m.bot:
            continue

        if blacklist and blacklist in m.roles:
            continue

        if whitelist and whitelist in m.roles:
            whitelist_to_move.append(m)
            continue

        score = waited(m.id) - (matches_last_24h(m.id) * 2)

        eligible.append((score, m))

    eligible.sort(key=lambda x: x[0], reverse=True)

    selected = [m for score, m in eligible[:amount]]

    if not selected and not whitelist_to_move:
        return await interaction.followup.send("No players in Public VC.")

    # ========= EXECUTE =========

    tasks = []
    lines = []

    # WHITELIST MOVE (ONLY FROM PUBLIC VC)

    for m in whitelist_to_move:

        async def wl_task(member=m):

            try:

                if code_role not in member.roles:
                    await member.add_roles(code_role)

                if (
                    member.voice
                    and member.voice.channel
                    and member.voice.channel.id == PUBLIC_VC_ID
                ):
                    await member.move_to(closed_vc)

            except:
                pass

        tasks.append(wl_task())

    # NORMAL PLAYERS

    for m in selected:

        current_match.add(m.id)

        uid = str(m.id)

        stats = player_stats.setdefault(
            uid,
            {"plays": [], "waited": 0}
        )

        prev_wait = stats["waited"]

        stats["plays"].append(now())

        stats["waited"] = 0

        async def sel_task(member=m):

            try:

                if code_role not in member.roles:
                    await member.add_roles(code_role)

                if (
                    member.voice
                    and member.voice.channel
                    and member.voice.channel.id == PUBLIC_VC_ID
                ):
                    await member.move_to(closed_vc)

            except:
                pass

        tasks.append(sel_task())

        lines.append(
            f"✅ {m.display_name} — matches:{len(stats['plays'])} after:{prev_wait}"
        )

    if tasks:
        await asyncio.gather(*tasks)

    # UPDATE WAIT COUNTER

    for m in public_vc.members:

        if m.bot:
            continue

        if m.id in current_match:
            continue

        player_stats.setdefault(
            str(m.id),
            {"plays": [], "waited": 0}
        )["waited"] += 1

    save_data()

    await interaction.followup.send(
        "### Selection Complete\n\n" +
        "\n".join(lines)
    )
